import httpx
from fastapi import HTTPException
from ..utilities.logging_config import logger
from ..database.database import update_payment_status
from ..services.config_service import get_empresa_credentials

async def get_asaas_headers(empresa_id: str):
    """
    Retorna os headers necessários para autenticação na API do Asaas da empresa específica.
    """
    credentials = get_empresa_credentials(empresa_id)
    if not credentials or not credentials.get("asaas_api_key"):
        raise ValueError(f"API Key do Asaas não encontrada para empresa {empresa_id}")

    return {
        "Authorization": f"Bearer {credentials['asaas_api_key']}",
        "Content-Type": "application/json"
    }

async def create_asaas_payment(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer: dict,
    card_data: dict = None,
    installments: int = 1
):
    """
    Cria um pagamento no Asaas para a empresa específica.
    """

    # Busca credenciais da empresa
    credentials = get_empresa_credentials(empresa_id)
    headers = await get_asaas_headers(empresa_id)

    # Define a URL correta
    use_sandbox = credentials.get("use_sandbox", "true").lower() == "true"
    asaas_api_url = "https://sandbox.asaas.com/api/v3/payments" if use_sandbox else "https://api.asaas.com/v3/payments"
    
    # Webhook dinâmico por empresa
    webhook_pix = credentials.get("webhook_pix")

    if payment_type == "pix":
        payload = {
            "customer": customer.get("id"),
            "value": amount,
            "billingType": "PIX",
            "dueDate": customer.get("due_date"),
            "description": f"Pagamento Pix {transaction_id}",
            "externalReference": transaction_id,
            "postalService": False,
            "callbackUrl": webhook_pix
        }
    elif payment_type == "credit_card":
        if not card_data:
            raise HTTPException(status_code=400, detail="Dados do cartão são obrigatórios para pagamentos com cartão de crédito.")

        installments = max(1, min(installments, 12))  # Garante que o número de parcelas está dentro do limite

        payload = {
            "customer": customer.get("id"),
            "value": amount,
            "billingType": "CREDIT_CARD",
            "dueDate": customer.get("due_date"),
            "description": f"Pagamento Cartão {transaction_id}",
            "externalReference": transaction_id,
            "callbackUrl": webhook_pix,
            "installmentCount": installments,
            "creditCard": {
                "holderName": card_data["cardholder_name"],
                "number": card_data["card_number"],
                "expiryMonth": card_data["expiration_month"],
                "expiryYear": card_data["expiration_year"],
                "ccv": card_data["security_code"]
            },
            "creditCardHolderInfo": {
                "name": card_data["cardholder_name"],
                "email": customer.get("email"),
                "cpfCnpj": customer.get("document"),
                "postalCode": customer.get("postal_code"),
                "addressNumber": customer.get("address_number"),
                "phone": customer.get("phone")
            }
        }
    else:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(asaas_api_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao criar pagamento no Asaas: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao processar pagamento no Asaas")
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao criar pagamento no Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao processar pagamento no Asaas")

async def get_asaas_payment_status(empresa_id: str, transaction_id: str):
    """Verifica o status de um pagamento no Asaas para a empresa específica."""
    
    headers = await get_asaas_headers(empresa_id)
    credentials = get_empresa_credentials(empresa_id)
    use_sandbox = credentials.get("use_sandbox", "true").lower() == "true"
    asaas_api_url = "https://sandbox.asaas.com/api/v3/payments" if use_sandbox else "https://api.asaas.com/v3/payments"

    url = f"{asaas_api_url}?externalReference={transaction_id}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data.get("data"):
                return data["data"][0]
            else:
                logger.warning(f"Pagamento não encontrado para transaction_id: {transaction_id}")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP ao buscar status do pagamento no Asaas: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao buscar status do pagamento no Asaas")
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão ao buscar status do pagamento no Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao buscar status do pagamento no Asaas")

async def process_asaas_webhook(data: dict):
    """Processa notificações recebidas do webhook do Asaas."""
    try:
        transaction_id = data.get("externalReference")
        status = data.get("status")

        if transaction_id and status:
            update_payment_status(transaction_id, status)
            logger.info(f"Pagamento {transaction_id} atualizado para status: {status}")
            return {"message": f"Pagamento {transaction_id} atualizado com sucesso"}

        return {"message": "Nenhuma transação processada"}
    except Exception as e:
        logger.error(f"Erro ao processar webhook do Asaas: {str(e)}")
        raise
