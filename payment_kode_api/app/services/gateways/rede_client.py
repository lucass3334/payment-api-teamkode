import httpx
from base64 import b64encode
from fastapi import HTTPException
from ...utilities.logging_config import logger
from ..config_service import get_empresa_credentials
from .asaas_client import create_asaas_payment  # Importando Asaas como fallback
import asyncio

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

async def get_rede_access_token(empresa_id: str, retries: int = 2):
    """
    Obtém um token de acesso para autenticação na API da Rede, com tentativas de fallback.
    """
    credentials = get_empresa_credentials(empresa_id)
    if not credentials:
        raise ValueError(f"Configuração da Rede não encontrada para empresa {empresa_id}")

    auth_url = "https://api.userede.com.br/auth"

    headers = await get_rede_headers(empresa_id)

    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(retries):
            try:
                response = await client.post(auth_url, headers=headers)
                response.raise_for_status()
                return response.json().get("access_token")

            except httpx.HTTPStatusError as e:
                logger.error(f"Erro HTTP ao obter token da Rede (tentativa {attempt+1}): {e.response.status_code} - {e.response.text}")
                if e.response.status_code in {401, 403}:  # Credenciais inválidas
                    raise HTTPException(status_code=401, detail="Credenciais inválidas para a Rede")

            except httpx.RequestError as e:
                logger.warning(f"Erro de conexão ao autenticar na Rede (tentativa {attempt+1}): {e}")

            await asyncio.sleep(2)

    raise HTTPException(status_code=500, detail=f"Falha ao obter token da Rede para empresa {empresa_id} após {retries} tentativas")

async def create_rede_payment(
    empresa_id: str, 
    transaction_id: str, 
    amount: int, 
    card_data: dict, 
    installments: int = 1
):
    """
    Cria um pagamento via Cartão de Crédito na Rede com suporte a parcelamento.
    Se a Rede falhar, automaticamente tenta o Asaas como fallback.
    """
    try:
        token = await get_rede_access_token(empresa_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        transaction_url = "https://api.userede.com.br/ecomm/v1/transactions"

        payload = {
            "capture": True,
            "reference": transaction_id,
            "amount": amount,
            "installments": installments,
            "kind": "credit",
            "card": {
                "number": card_data["card_number"],
                "expirationMonth": card_data["expiration_month"],
                "expirationYear": card_data["expiration_year"],
                "securityCode": card_data["security_code"],
                "holderName": card_data["cardholder_name"]
            }
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(transaction_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao criar pagamento na Rede: {e.response.status_code} - {e.response.text}")
        if e.response.status_code in {400, 402, 403}:  
            raise HTTPException(status_code=e.response.status_code, detail="Pagamento recusado pela Rede")

    except httpx.RequestError as e:
        logger.error(f"Erro de conexão ao criar pagamento na Rede: {e}")
        raise HTTPException(status_code=500, detail="Erro de conexão ao processar pagamento na Rede")

    except Exception as e:
        logger.error(f"Erro inesperado na Rede: {str(e)}")
    
    # Se falhar na Rede, tenta o Asaas como fallback
    try:
        logger.warning(f"Pagamento falhou na Rede, tentando fallback via Asaas para {transaction_id}")
        return await create_asaas_payment(
            empresa_id=empresa_id,
            amount=amount / 100,  # Conversão para reais
            payment_type="credit_card",
            transaction_id=transaction_id,
            customer={},  # Ajustar cliente se necessário
            card_data=card_data,
            installments=installments
        )
    except Exception as fallback_error:
        logger.error(f"Erro no fallback via Asaas para {transaction_id}: {str(fallback_error)}")
        raise HTTPException(status_code=500, detail="Falha no pagamento via Rede e Asaas")
