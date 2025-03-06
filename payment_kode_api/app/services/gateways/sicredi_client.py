import httpx
import base64
import asyncio
from fastapi import HTTPException
from ...utilities.logging_config import logger
from ...database.database import update_payment_status
from ...database.redis_client import get_redis_client  # 🔹 Agora utilizamos Redis
from ..config_service import get_empresa_credentials, create_temp_cert_files


async def get_access_token(empresa_id: str, retries: int = 2):
    """Obtém um token OAuth2 para a API Pix do Sicredi, reutilizando via Redis."""
    
    redis = get_redis_client()

    # 🔹 Verifica se há um token válido armazenado no Redis
    cached_token = redis.get(f"sicredi_token:{empresa_id}")
    if cached_token:
        return cached_token  # 🔥 Retorna o token armazenado

    credentials = get_empresa_credentials(empresa_id)
    if not credentials:
        logger.error(f"Credenciais do Sicredi não encontradas para empresa {empresa_id}")
        raise ValueError(f"Credenciais do Sicredi não encontradas para empresa {empresa_id}")

    sicredi_client_id = credentials["sicredi_client_id"]
    sicredi_client_secret = credentials["sicredi_client_secret"]
    sicredi_env = credentials.get("sicredi_env", "production").lower()

    auth_url = "https://api-h.sicredi.com.br/oauth/token" if sicredi_env == "homologation" else "https://api-pix.sicredi.com.br/oauth/token"

    auth_header = base64.b64encode(f"{sicredi_client_id}:{sicredi_client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials", "scope": "cob.read cob.write pix.read"}

    cert_files = create_temp_cert_files(empresa_id)
    if not all(cert_files.values()):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    async with httpx.AsyncClient(cert=(cert_files["cert"], cert_files["key"]), 
                                 verify=cert_files["ca"], timeout=10) as client:
        for attempt in range(retries):
            try:
                response = await client.post(auth_url, data=data, headers=headers)
                response.raise_for_status()
                token_data = response.json()

                access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)  # Padrão: 1 hora

                if access_token:
                    redis.setex(f"sicredi_token:{empresa_id}", expires_in - 60, access_token)  # 🔥 Salva no Redis com expiração
                    return access_token

            except httpx.HTTPStatusError as e:
                logger.error(f"Erro HTTP na autenticação do Sicredi: {e.response.status_code} - {e.response.text}")
                if e.response.status_code in {401, 403}:  # Credenciais inválidas
                    raise

            await asyncio.sleep(2)

    raise RuntimeError(f"Falha ao obter token do Sicredi para empresa {empresa_id}")


async def create_sicredi_pix_payment(empresa_id: str, amount: float, chave_pix: str, txid: str):
    """Cria um pagamento Pix no Sicredi com autenticação mTLS."""

    token = await get_access_token(empresa_id)
    credentials = get_empresa_credentials(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = "https://api-h.sicredi.com.br/api/v2" if sicredi_env == "homologation" else "https://api-pix.sicredi.com.br/api/v2"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "calendario": {"expiracao": 900},
        "devedor": {"chave": chave_pix},
        "valor": {"original": f"{amount:.2f}"},
        "txid": txid
    }

    cert_files = create_temp_cert_files(empresa_id)
    if not all(cert_files.values()):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    async with httpx.AsyncClient(cert=(cert_files["cert"], cert_files["key"]), 
                                 verify=cert_files["ca"], timeout=15) as client:
        try:
            response = await client.post(f"{base_url}/cob", json=payload, headers=headers)
            response.raise_for_status()
            response_data = response.json()

            await register_sicredi_webhook(empresa_id, chave_pix)

            return {
                "qr_code": response_data.get("pixCopiaECola"),
                "pix_link": response_data.get("location"),
                "status": response_data.get("status"),
                "expiration": response_data["calendario"]["expiracao"]
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao criar pagamento Pix no Sicredi: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao processar pagamento via Sicredi")

        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao criar pagamento Pix no Sicredi: {e}")
            raise HTTPException(status_code=500, detail="Falha de conexão com o Sicredi")


async def register_sicredi_webhook(empresa_id: str, chave_pix: str):
    """Registra o webhook do Sicredi apenas se ainda não estiver cadastrado."""

    credentials = get_empresa_credentials(empresa_id)
    webhook_pix = credentials.get("webhook_pix")

    if not webhook_pix:
        logger.warning(f"WEBHOOK_PIX não configurado para empresa {empresa_id}. O Sicredi não será notificado.")
        return

    token = await get_access_token(empresa_id)

    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = "https://api-h.sicredi.com.br/api/v2" if sicredi_env == "homologation" else "https://api-pix.sicredi.com.br/api/v2"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    cert_files = create_temp_cert_files(empresa_id)
    if not all(cert_files.values()):
        raise ValueError(f"Certificados do Sicredi estão ausentes para empresa {empresa_id}")

    async with httpx.AsyncClient(cert=(cert_files["cert"], cert_files["key"]), 
                                 verify=cert_files["ca"], timeout=10) as client:
        # 🔹 Verifica se já existe um webhook cadastrado
        response = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)
        if response.status_code == 200:
            logger.info(f"Webhook já cadastrado para chave {chave_pix}, evitando duplicação.")
            return

        payload = {"webhookUrl": webhook_pix}

        try:
            response = await client.put(f"{base_url}/webhook/{chave_pix}", json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Webhook registrado com sucesso para chave {chave_pix}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro ao registrar webhook: {e.response.status_code} - {e.response.text}")
            raise
