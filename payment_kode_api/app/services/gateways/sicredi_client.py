import httpx
import base64
import asyncio
from fastapi import HTTPException
from typing import Any

from ...utilities.logging_config import logger
from ...database.redis_client import get_redis_client
from ..config_service import get_empresa_credentials, load_certificates_from_bucket
from utilities.cert_utils import get_md5, build_ssl_context_from_memory

# 🔧 Timeout padrão para conexões Sicredi
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def get_access_token(empresa_id: str, retries: int = 2):
    redis = get_redis_client()
    redis_key = f"sicredi_token:{empresa_id}"
    cached_token = redis.get(redis_key)

    if cached_token:
        return cached_token

    credentials = await get_empresa_credentials(empresa_id)
    if not credentials:
        raise ValueError("❌ Credenciais do Sicredi não configuradas corretamente.")

    sicredi_client_id = credentials["sicredi_client_id"]
    sicredi_client_secret = credentials["sicredi_client_secret"]
    sicredi_env = credentials.get("sicredi_env", "production").lower()

    auth_url = (
        "https://api-h.pix.sicredi.com.br/oauth/token"
        if sicredi_env == "homologation"
        else "https://api-pix.sicredi.com.br/oauth/token"
    )
    auth_header = base64.b64encode(f"{sicredi_client_id}:{sicredi_client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/json"
    }

    full_url = f"{auth_url}?grant_type=client_credentials&scope=cob.read%20cob.write%20pix.read"

    cert_data = await load_certificates_from_bucket(empresa_id)

    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=cert_data["cert_path"],
            key_pem=cert_data["key_path"],
            ca_pem=cert_data["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro ao montar SSLContext: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar certificados da empresa.")

    logger.debug(f"🔑 cert.pem md5: {get_md5(cert_data['cert_path'])}")
    logger.debug(f"🔑 key.key md5: {get_md5(cert_data['key_path'])}")
    logger.debug(f"🔑 ca.pem   md5: {get_md5(cert_data['ca_path'])}")

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(
                verify=ssl_ctx,
                timeout=TIMEOUT
            ) as client:
                logger.info(f"🔐 Tentativa {attempt + 1} - Token Sicredi via {full_url}")
                response = await client.post(full_url, headers=headers)
                response.raise_for_status()

                token_data = response.json()
                access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)

                if access_token:
                    redis.setex(redis_key, expires_in - 60, access_token)
                    return access_token

                logger.error(f"❌ Token ausente na resposta da Sicredi: {token_data}")
                break

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} na autenticação Sicredi")
            logger.debug(f"🔎 URL: {e.request.url}")
            logger.debug(f"🔎 Resposta: {e.response.text}")
            redis.delete(redis_key)
            if e.response.status_code in {401, 403} and attempt + 1 >= retries:
                raise HTTPException(status_code=410, detail="Credenciais Sicredi inválidas ou expiradas.")
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao requisitar token: {str(e)}")
            raise

        await asyncio.sleep(2)

    raise RuntimeError(f"❌ Falha ao obter token do Sicredi para empresa {empresa_id}")


async def create_sicredi_pix_payment(empresa_id: str, **payload: Any):
    token = await get_access_token(empresa_id)
    credentials = await get_empresa_credentials(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.pix.sicredi.com.br/api/v2"
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

    cert_data = await load_certificates_from_bucket(empresa_id)

    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=cert_data["cert_path"],
            key_pem=cert_data["key_path"],
            ca_pem=cert_data["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro ao montar SSLContext (cobrança): {str(e)}")
        raise HTTPException(status_code=500, detail="Erro com os certificados da empresa.")

    async with httpx.AsyncClient(
        verify=ssl_ctx,
        timeout=TIMEOUT
    ) as client:
        logger.info(f"📤 Enviando cobrança Pix para Sicredi: {base_url}/cob - txid: {body['txid']}")
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


async def register_sicredi_webhook(empresa_id: str, chave_pix: str):
    credentials = await get_empresa_credentials(empresa_id)
    webhook_pix = credentials.get("webhook_pix")

    if not webhook_pix:
        logger.warning(f"⚠️ WEBHOOK_PIX não configurado para empresa {empresa_id}.")
        return

    token = await get_access_token(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.pix.sicredi.com.br/api/v2"
        if sicredi_env == "homologation"
        else "https://api-pix.sicredi.com.br/api/v2"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    cert_data = await load_certificates_from_bucket(empresa_id)

    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=cert_data["cert_path"],
            key_pem=cert_data["key_path"],
            ca_pem=cert_data["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro ao montar SSLContext (webhook): {str(e)}")
        raise HTTPException(status_code=500, detail="Erro com os certificados da empresa.")

    async with httpx.AsyncClient(
        verify=ssl_ctx,
        timeout=TIMEOUT
    ) as client:
        logger.info(f"🔍 Verificando webhook para chave Pix: {chave_pix}")
        response = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)

        if response.status_code == 200:
            logger.info(f"✅ Webhook já configurado para {chave_pix}")
            return

        payload = {"webhookUrl": webhook_pix}
        logger.info(f"📤 Registrando webhook para chave Pix: {chave_pix}")
        response = await client.put(f"{base_url}/webhook/{chave_pix}", json=payload, headers=headers)
        response.raise_for_status()

        logger.info(f"✅ Webhook registrado com sucesso para chave Pix: {chave_pix}")
        return response.json()


# 🔧 (Comentado: método antigo baseado em arquivos)
# from utilities.cert_utils import write_temp_cert
# async def get_cert_paths_from_memory(empresa_id: str):
#     cert_data = await load_certificates_from_bucket(empresa_id)
#     if not cert_data:
#         raise ValueError(f"❌ Certificados ausentes ou inválidos para empresa {empresa_id}")
#     cert_file = write_temp_cert(cert_data["cert_path"], ".pem")
#     key_file = write_temp_cert(cert_data["key_path"], ".key")
#     ca_file = write_temp_cert(cert_data["ca_path"], ".pem")
#     logger.info(f"🔐 Certificados temporários criados:")
#     logger.debug(f"🔑 cert.pem md5: {get_md5(cert_data['cert_path'])}")
#     logger.debug(f"🔑 key.key md5: {get_md5(cert_data['key_path'])}")
#     logger.debug(f"🔑 ca.pem   md5: {get_md5(cert_data['ca_path'])}")
#     return cert_file, key_file, ca_file