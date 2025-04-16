import httpx
import certifi
import base64
import asyncio
import os
from fastapi import HTTPException
from ...utilities.logging_config import logger
from ...database.database import update_payment_status
from ...database.redis_client import get_redis_client
from ..config_service import get_empresa_credentials
from typing import Any


def get_cert_paths(empresa_id: str):
    # Atualizado para refletir o novo volume persistente montado em /data
    base_dir = f"/data/certificados/{empresa_id}"
    cert_path = os.path.join(base_dir, "sicredi-cert.pem")
    key_path = os.path.join(base_dir, "sicredi-key.pem")
    return cert_path, key_path


async def get_access_token(empresa_id: str, retries: int = 2):
    redis = get_redis_client()
    cached_token = redis.get(f"sicredi_token:{empresa_id}")
    if cached_token:
        return cached_token

    credentials = await get_empresa_credentials(empresa_id)
    if not credentials:
        logger.error(f"❌ Credenciais do Sicredi não encontradas para empresa {empresa_id}")
        raise ValueError(f"❌ Credenciais do Sicredi não encontradas para empresa {empresa_id}")

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
        "Content-Type": "application/json"
    }

    full_url = f"{auth_url}?grant_type=client_credentials&scope=cob.read%20cob.write%20pix.read"

    cert_path, key_path = get_cert_paths(empresa_id)
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise ValueError(f"❌ Certificados não encontrados para empresa {empresa_id} em disco")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_path, key_path),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            for attempt in range(retries):
                try:
                    logger.info(f"🔐 Tentativa {attempt + 1} - Token Sicredi via {full_url}")
                    response = await client.post(full_url, headers=headers)
                    response.raise_for_status()
                    token_data = response.json()

                    access_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)

                    if access_token:
                        redis.setex(f"sicredi_token:{empresa_id}", expires_in - 60, access_token)
                        return access_token

                except httpx.HTTPStatusError as e:
                    logger.error(f"❌ HTTP {e.response.status_code} na autenticação Sicredi")
                    logger.debug(f"🔎 URL: {e.request.url}")
                    logger.debug(f"🔎 Resposta: {e.response.text}")
                    if e.response.status_code in {401, 403}:
                        raise

                await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao requisitar token: {str(e)}")
        raise

    raise RuntimeError(f"❌ Falha ao obter token do Sicredi para empresa {empresa_id}")


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

    cert_path, key_path = get_cert_paths(empresa_id)
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise ValueError(f"❌ Certificados não encontrados para empresa {empresa_id} em disco")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_path, key_path),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            logger.info(f"📤 Enviando cobrança para Sicredi: {base_url}/cob")
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


async def register_sicredi_webhook(empresa_id: str, chave_pix: str):
    credentials = await get_empresa_credentials(empresa_id)
    webhook_pix = credentials.get("webhook_pix")

    if not webhook_pix:
        logger.warning(f"⚠️ WEBHOOK_PIX não configurado para empresa {empresa_id}.")
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

    cert_path, key_path = get_cert_paths(empresa_id)
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise ValueError(f"❌ Certificados não encontrados para empresa {empresa_id} em disco")

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(
            cert=(cert_path, key_path),
            verify=certifi.where(),
            timeout=timeout
        ) as client:
            logger.info(f"🔍 Verificando webhook para chave {chave_pix}")
            response = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)

            if response.status_code == 200:
                logger.info(f"✅ Webhook já existe para chave {chave_pix}")
                return

            payload = {"webhookUrl": webhook_pix}
            logger.info(f"📤 Registrando webhook para chave {chave_pix}")

            response = await client.put(f"{base_url}/webhook/{chave_pix}", json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"✅ Webhook registrado com sucesso para {chave_pix}")
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Erro HTTP ao registrar webhook: {e.response.status_code}")
        logger.debug(f"❌ URL: {e.request.url}")
        logger.debug(f"❌ Resposta: {e.response.text}")
        raise
