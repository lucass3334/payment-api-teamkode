
# services/gateways/sicredi_client.py

import httpx
import base64
import asyncio
from fastapi import HTTPException
from typing import Any

from ...utilities.logging_config import logger
from ..config_service import get_empresa_credentials, load_certificates_from_bucket
from ...utilities.cert_utils import get_md5, build_ssl_context_from_memory

# 🔧 Timeout padrão para conexões Sicredi
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def get_access_token(empresa_id: str, retries: int = 2) -> str:
    """
    Solicita um novo token diretamente na API Sicredi via client_credentials.
    """
    credentials = await get_empresa_credentials(empresa_id)
    if not credentials:
        raise ValueError("❌ Credenciais do Sicredi não configuradas corretamente.")

    client_id = credentials["sicredi_client_id"]
    client_secret = credentials["sicredi_client_secret"]
    env = credentials.get("sicredi_env", "production").lower()

    auth_url = (
        "https://api-h.pix.sicredi.com.br/oauth/token"
        if env == "homologation"
        else "https://api-pix.sicredi.com.br/oauth/token"
    )
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/json"
    }
    full_url = f"{auth_url}?grant_type=client_credentials&scope=cob.read%20cob.write%20pix.read"

    certs = await load_certificates_from_bucket(empresa_id)
    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=certs["cert_path"],
            key_pem=certs["key_path"],
            ca_pem=certs["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro ao montar SSLContext: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar certificados da empresa.")

    logger.debug(f"🔑 cert.pem md5: {get_md5(certs['cert_path'])}")
    logger.debug(f"🔑 key.key md5:  {get_md5(certs['key_path'])}")
    logger.debug(f"🔑 ca.pem md5:   {get_md5(certs['ca_path'])}")

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
                logger.info(f"🔐 Sicredi token attempt {attempt} → {full_url}")
                resp = await client.post(full_url, headers=headers)
                resp.raise_for_status()

                data = resp.json()
                token = data.get("access_token")
                if token:
                    return token

                logger.error(f"❌ Nenhum access_token no retorno Sicredi: {data}")
                break

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.error(f"❌ HTTP {code} obtendo token Sicredi")
            if code in (401, 403) and attempt == retries:
                raise HTTPException(status_code=410, detail="Credenciais Sicredi inválidas ou expiradas.")
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao requisitar token Sicredi: {e}")
            raise

        await asyncio.sleep(2)

    raise RuntimeError(f"❌ Falha ao obter token Sicredi para empresa {empresa_id}")


async def create_sicredi_pix_payment(empresa_id: str, **payload: Any) -> dict:
    """
    Cria uma cobrança Pix no Sicredi usando PUT /cob/{txid}.
    """
    # import dinâmico para quebrar ciclo
    from payment_kode_api.app.database.database import get_sicredi_token_or_refresh

    token = await get_sicredi_token_or_refresh(empresa_id)
    if not token:
        raise HTTPException(status_code=401, detail="Token Sicredi inválido ou expirado.")

    credentials = await get_empresa_credentials(empresa_id)
    env = credentials.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.pix.sicredi.com.br/api/v2"
        if env == "homologation"
        else "https://api-pix.sicredi.com.br/api/v2"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    txid = payload["txid"]
    # monta o corpo sem repetir o txid
    body = {
        "calendario": {"expiracao": 900},
        "chave": payload["chave"],
        "valor": {"original": payload["valor"]["original"]},
    }
    if "devedor" in payload:
        body["devedor"] = payload["devedor"]
    if "solicitacaoPagador" in payload:
        body["solicitacaoPagador"] = payload["solicitacaoPagador"]

    certs = await load_certificates_from_bucket(empresa_id)
    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=certs["cert_path"],
            key_pem=certs["key_path"],
            ca_pem=certs["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro SSLContext (cobrança): {e}")
        raise HTTPException(status_code=500, detail="Erro com certificados da empresa.")

    # usa PUT com txid na URL
    async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
        txid = payload["txid"]
        endpoint = f"{base_url}/cob/{txid}"

        # 1) Logue endpoint e body antes de enviar
        logger.info(f"📤 Enviando Pix para Sicredi: PUT {endpoint} – body: {body}")

        resp = await client.put(endpoint, json=body, headers=headers)

        # 2) Capture e logue qualquer erro HTTP
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Sicredi retornou HTTP {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Erro no gateway Sicredi: {e.response.text}"
            ) from e

        data = resp.json()

        # 3) Registra webhook no Sicredi após criar cobrança
        await register_sicredi_webhook(empresa_id, payload["chave"])

        # 4) Retorna dados ao chamador
        return {
            "qr_code": data.get("pixCopiaECola"),
            "pix_link": data.get("location"),
            "status": data.get("status"),
            "expiration": data["calendario"]["expiracao"]
        }

async def register_sicredi_webhook(empresa_id: str, chave_pix: str) -> Any:
    """
    Consulta e, se ausente, registra o webhook no Sicredi via PUT /webhook/{chave}.
    """
    from payment_kode_api.app.database.database import get_sicredi_token_or_refresh

    creds = await get_empresa_credentials(empresa_id)
    webhook_url = creds.get("webhook_pix")
    if not webhook_url:
        logger.warning(f"⚠️ WEBHOOK_PIX não configurado para empresa {empresa_id}")
        return

    token = await get_sicredi_token_or_refresh(empresa_id)
    env = creds.get("sicredi_env", "production").lower()
    base_url = (
        "https://api-h.pix.sicredi.com.br/api/v2"
        if env == "homologation"
        else "https://api-pix.sicredi.com.br/api/v2"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    certs = await load_certificates_from_bucket(empresa_id)
    try:
        ssl_ctx = build_ssl_context_from_memory(
            cert_pem=certs["cert_path"],
            key_pem=certs["key_path"],
            ca_pem=certs["ca_path"]
        )
    except Exception as e:
        logger.error(f"❌ Erro SSLContext (webhook): {e}")
        raise HTTPException(status_code=500, detail="Erro com certificados da empresa.")

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
        # verifica se já existe
        resp = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)
        if resp.status_code == 200:
            logger.info(f"✅ Webhook já existe para {chave_pix}")
            return

        # registra novo webhook
        logger.info(f"📤 Registrando webhook Sicredi para {chave_pix}")
        resp = await client.put(
            f"{base_url}/webhook/{chave_pix}",
            json={"webhookUrl": webhook_url},
            headers=headers
        )
        resp.raise_for_status()
        logger.info(f"✅ Webhook Sicredi registrado para {chave_pix}")
        return resp.json()



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