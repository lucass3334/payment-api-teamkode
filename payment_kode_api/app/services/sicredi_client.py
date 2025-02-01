import httpx
import base64
from ..utilities.logging_config import logger
from ..database.database import update_payment_status
from ..services.config_service import get_empresa_credentials, create_temp_cert_files

async def get_access_token(empresa_id: str):
    """Obtém um token OAuth2 para autenticação com a API Pix do Sicredi, específico para a empresa."""
    
    # Busca as credenciais específicas da empresa
    credentials = get_empresa_credentials(empresa_id)
    if not credentials:
        raise ValueError(f"Credenciais do Sicredi não encontradas para empresa {empresa_id}")

    sicredi_client_id = credentials["sicredi_client_id"]
    sicredi_client_secret = credentials["sicredi_client_secret"]

    # Define a URL de autenticação correta
    sicredi_env = credentials.get("sicredi_env", "production").lower()
    auth_url = "https://api-h.sicredi.com.br/oauth/token" if sicredi_env == "homologation" else "https://api-pix.sicredi.com.br/oauth/token"

    headers = {
        "Authorization": f"Basic {httpx.auth._basic_auth_str(sicredi_client_id, sicredi_client_secret)}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials", "scope": "cob.read+cob.write+pix.read"}

    # Carrega certificados dinâmicos para a empresa
    cert_files = create_temp_cert_files(empresa_id)

    async with httpx.AsyncClient(cert=(cert_files["sicredi_cert_base64"], cert_files["sicredi_key_base64"]), verify=cert_files["sicredi_ca_base64"]) as client:
        try:
            response = await client.post(auth_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json().get("access_token")
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP na autenticação do Sicredi: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao autenticar no Sicredi: {e}")
            raise

async def create_sicredi_pix_payment(empresa_id: str, amount: float, chave_pix: str, txid: str):
    """Cria um pagamento Pix no Sicredi para a empresa específica."""
    
    token = await get_access_token(empresa_id)
    credentials = get_empresa_credentials(empresa_id)
    
    # Define a URL correta para pagamentos
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

    # Carrega certificados dinâmicos para a empresa
    cert_files = create_temp_cert_files(empresa_id)

    async with httpx.AsyncClient(cert=(cert_files["sicredi_cert_base64"], cert_files["sicredi_key_base64"]), verify=cert_files["sicredi_ca_base64"]) as client:
        try:
            response = await client.post(f"{base_url}/cob", json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            response_data = response.json()

            # Registra webhook automaticamente
            await register_sicredi_webhook(empresa_id, chave_pix)

            return {
                "qr_code": response_data.get("pixCopiaECola"),
                "pix_link": response_data.get("location"),
                "status": response_data.get("status"),
                "expiration": response_data["calendario"]["expiracao"]
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao criar pagamento Pix no Sicredi: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao criar pagamento Pix no Sicredi: {e}")
            raise

async def register_sicredi_webhook(empresa_id: str, chave_pix: str):
    """Registra o webhook do Sicredi para notificações de pagamento da empresa específica."""
    
    credentials = get_empresa_credentials(empresa_id)
    webhook_pix = credentials.get("webhook_pix")

    if not webhook_pix:
        logger.warning(f"WEBHOOK_PIX não configurado para empresa {empresa_id}. O Sicredi não será notificado.")
        return

    token = await get_access_token(empresa_id)

    # Define a URL correta para o webhook
    sicredi_env = credentials.get("sicredi_env", "production").lower()
    base_url = "https://api-h.sicredi.com.br/api/v2" if sicredi_env == "homologation" else "https://api-pix.sicredi.com.br/api/v2"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"webhookUrl": webhook_pix}

    # Carrega certificados dinâmicos para a empresa
    cert_files = create_temp_cert_files(empresa_id)

    async with httpx.AsyncClient(cert=(cert_files["sicredi_cert_base64"], cert_files["sicredi_key_base64"]), verify=cert_files["sicredi_ca_base64"]) as client:
        try:
            response = await client.put(f"{base_url}/webhook/{chave_pix}", json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Webhook do Sicredi registrado com sucesso para empresa {empresa_id}, chave {chave_pix}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao registrar webhook no Sicredi: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao registrar webhook no Sicredi: {e}")
            raise

async def process_sicredi_webhook(data: dict):
    """Processa notificações recebidas do webhook do Sicredi."""
    try:
        if "pix" in data:
            for pix in data["pix"]:
                transaction_id = pix.get("txid")
                status = pix.get("status")

                if transaction_id and status:
                    update_payment_status(transaction_id, status)
                    logger.info(f"Pagamento {transaction_id} atualizado para status: {status}")
                    return {"message": f"Pagamento {transaction_id} atualizado com sucesso"}

        return {"message": "Nenhuma transação processada"}
    except Exception as e:
        logger.error(f"Erro ao processar webhook do Sicredi: {str(e)}")
        raise
