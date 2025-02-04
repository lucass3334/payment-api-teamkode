import httpx
from base64 import b64encode
from fastapi import HTTPException
from ..utilities.logging_config import logger
from ..services.config_service import get_empresa_credentials

async def get_rede_headers(empresa_id: str):
    """
    Retorna os headers necessários para autenticação na API da Rede para uma empresa específica.
    """
    credentials = get_empresa_credentials(empresa_id)
    if not credentials or not credentials.get("rede_pv") or not credentials.get("rede_api_key"):
        raise ValueError(f"Credenciais da Rede não encontradas para empresa {empresa_id}")

    auth_header = b64encode(f"{credentials['rede_pv']}:{credentials['rede_api_key']}".encode()).decode()
    
    return {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/json",
    }

async def get_rede_access_token(empresa_id: str):
    """
    Obtém um token de acesso para autenticação na API da Rede.
    """
    credentials = get_empresa_credentials(empresa_id)
    if not credentials:
        raise ValueError(f"Configuração da Rede não encontrada para empresa {empresa_id}")

    auth_url = "https://api.userede.com.br/auth"

    headers = await get_rede_headers(empresa_id)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(auth_url, headers=headers)
            response.raise_for_status()
            return response.json().get("access_token")
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao obter token da Rede: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao autenticar na Rede")
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao autenticar na Rede: {e}")
            raise HTTPException(status_code=500, detail="Erro de conexão ao autenticar na Rede")

async def create_rede_payment(
    empresa_id: str, 
    transaction_id: str, 
    amount: int, 
    card_data: dict, 
    installments: int = 1
):
    """
    Cria um pagamento via Cartão de Crédito na Rede com suporte a parcelamento.

    Args:
        empresa_id (str): ID da empresa que está realizando a transação.
        transaction_id (str): ID da transação.
        amount (int): Valor da transação em centavos.
        card_data (dict): Dados do cartão de crédito.
        installments (int, opcional): Número de parcelas (padrão é 1).

    Returns:
        dict: Resposta da API da Rede.
    """
    token = await get_rede_access_token(empresa_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    transaction_url = "https://api.userede.com.br/ecomm/v1/transactions"

    payload = {
        "capture": True,  # Define se a transação será capturada automaticamente
        "reference": transaction_id,
        "amount": amount,
        "installments": installments,
        "kind": "credit",  # Define que é uma transação de crédito
        "card": {
            "number": card_data["card_number"],
            "expirationMonth": card_data["expiration_month"],
            "expirationYear": card_data["expiration_year"],
            "securityCode": card_data["security_code"],
            "holderName": card_data["cardholder_name"]
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(transaction_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao criar pagamento na Rede: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao processar pagamento na Rede")
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao criar pagamento na Rede: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao processar pagamento na Rede")
