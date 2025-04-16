import httpx
import certifi
import base64
import asyncio
from fastapi import HTTPException
from ...utilities.logging_config import logger
from ...database.database import update_payment_status
from ...database.redis_client import get_redis_client
from ..config_service import get_empresa_credentials, create_temp_cert_files
from typing import Any


async def get_access_token(empresa_id: str, retries: int = 2):
    redis = get_redis_client()
    cached_token = redis.get(f"sicredi_token:{empresa_id}")
    if cached_token:
        return cached_token

    credentials = await get_empresa_credentials(empresa_id)
    if not credentials:
        logger.error(f"Credenciais do Sicredi não encontradas para empresa {empresa_id}")
        raise ValueError(f"Credenciais do Sicredi não encontradas para empresa {empresa_id}")

    sicredi_client_id = credentials["sicredi_client_id"]
    sicredi_client_secret = credentials["sicredi_client_secret"]
    sicredi_env = credentials.get("sicredi_env", "production").lower()

    auth_url = (
        "https://api-h.sicredi.com.br/oauth/token"
        if sicredi_env == "homologation"
        else "https://api-pix.sicredi.com.br/oauth/token"
    )
    auth_header = base64.b64encode(f"{sicredi_client_id}:{sicredi_client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Content-Type": "application/json"
    }

    params = {
        "grant_type": "client_credentials",
        "scope": "cob.read cob.write pix.read"
    }

    cert_files = await create_temp_cert_files(empresa_id)
    cleanup = cert_files.pop("cleanup", None)

    if not cert_files.get("cert_path") or not cert_files.get("key_path"):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_files["cert_path"], cert_files["key_path"]),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            for attempt in range(retries):
                try:
                    logger.info(f"🔍 Requisição OAuth Sicredi: {auth_url}")
                    logger.debug(f"🔍 Headers: {headers}")
                    logger.debug(f"🔍 Params: {params}")

                    response = await client.post(auth_url, headers=headers, params=params)
                    response.raise_for_status()
                    token_data = response.json()

                    access_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)

                    if access_token:
                        redis.setex(f"sicredi_token:{empresa_id}", expires_in - 60, access_token)
                        return access_token

                except httpx.HTTPStatusError as e:
                    logger.error(f"❌ HTTP {e.response.status_code} na autenticação Sicredi")
                    logger.debug(f"❌ Headers enviados: {e.request.headers}")
                    logger.debug(f"❌ URL requisitada: {e.request.url}")
                    logger.debug(f"❌ Corpo da resposta: {e.response.text}")
                    if e.response.status_code in {401, 403}:
                        raise

                await asyncio.sleep(2)
    finally:
        if cleanup:
            cleanup()

    raise RuntimeError(f"Falha ao obter token do Sicredi para empresa {empresa_id}")


async def create_sicredi_pix_payment(empresa_id: str, **payload: Any):
    token = await get_access_token(empresa_id)
    credentials = await get_empresa_credentials(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.sicredi.com.br/api/v2"
        if sicredi_env == "homologation"
        else "https://api-pix.sicredi.com.br/api/v2"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "calendario": {"expiracao": 900},
        "chave": payload["chave"],
        "valor": {"original": payload["valor"]["original"]},
        "txid": payload["txid"]
    }

    if "devedor" in payload:
        body["devedor"] = payload["devedor"]

    if "solicitacaoPagador" in payload:
        body["solicitacaoPagador"] = payload["solicitacaoPagador"]

    cert_files = await create_temp_cert_files(empresa_id)
    cleanup = cert_files.pop("cleanup", None)

    if not cert_files.get("cert_path") or not cert_files.get("key_path"):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_files["cert_path"], cert_files["key_path"]),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            try:
                logger.info(f"📤 Enviando cobrança para Sicredi: {base_url}/cob")
                logger.debug(f"📦 Body: {body}")
                logger.debug(f"📥 Headers: {headers}")

                response = await client.post(f"{base_url}/cob", json=body, headers=headers)
                response.raise_for_status()
                response_data = response.json()

                await register_sicredi_webhook(empresa_id, payload["chave"])

                return {
                    "qr_code": response_data.get("pixCopiaECola"),
                    "pix_link": response_data.get("location"),
                    "status": response_data.get("status"),
                    "expiration": response_data["calendario"]["expiracao"]
                }

            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Erro HTTP ao criar cobrança: {e.response.status_code}")
                logger.debug(f"❌ URL requisitada: {e.request.url}")
                logger.debug(f"❌ Resposta: {e.response.text}")
                raise HTTPException(status_code=e.response.status_code, detail="Erro ao processar pagamento via Sicredi")

            except httpx.RequestError as e:
                logger.error(f"❌ Falha de conexão com Sicredi: {e}")
                raise HTTPException(status_code=500, detail="Falha de conexão com o Sicredi")
    finally:
        if cleanup:
            cleanup()


async def register_sicredi_webhook(empresa_id: str, chave_pix: str):
    credentials = await get_empresa_credentials(empresa_id)
    webhook_pix = credentials.get("webhook_pix")

    if not webhook_pix:
        logger.warning(f"WEBHOOK_PIX não configurado para empresa {empresa_id}. O Sicredi não será notificado.")
        return

    token = await get_access_token(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.sicredi.com.br/api/v2"
        if sicredi_env == "homologation"
        else "https://api-pix.sicredi.com.br/api/v2"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    cert_files = await create_temp_cert_files(empresa_id)
    cleanup = cert_files.pop("cleanup", None)

    if not cert_files.get("cert_path") or not cert_files.get("key_path"):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_files["cert_path"], cert_files["key_path"]),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            logger.info(f"🔍 Verificando se webhook já está cadastrado: {base_url}/webhook/{chave_pix}")
            response = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)

            if response.status_code == 200:
                logger.info(f"✅ Webhook já existente para chave {chave_pix}")
                return

            payload = {"webhookUrl": webhook_pix}
            logger.info(f"📤 Registrando webhook para chave {chave_pix}")
            logger.debug(f"📦 Payload: {payload}")

            try:
                response = await client.put(f"{base_url}/webhook/{chave_pix}", json=payload, headers=headers)
                response.raise_for_status()
                logger.info(f"✅ Webhook registrado com sucesso para {chave_pix}")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Falha ao registrar webhook: {e.response.status_code}")
                logger.debug(f"❌ URL requisitada: {e.request.url}")
                logger.debug(f"❌ Resposta: {e.response.text}")
                raise
    finally:
        if cleanup:
            cleanup()
