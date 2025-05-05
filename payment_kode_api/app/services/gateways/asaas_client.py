import httpx
import asyncio
from fastapi import HTTPException
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from ...utilities.logging_config import logger
from ..config_service import get_empresa_credentials
from payment_kode_api.app.database.database import get_empresa_config
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.database.customers import get_or_create_asaas_customer

# ⏱️ Timeout padrão para conexões Asaas
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def get_asaas_headers(empresa_id: str) -> Dict[str, str]:
    """
    Retorna os headers necessários para autenticação na API do Asaas da empresa específica.
    """
    creds = await get_empresa_credentials(empresa_id)
    api_key = creds.get("asaas_api_key") if creds else None
    if not api_key:
        logger.error(f"❌ Asaas API key não configurada para empresa {empresa_id}")
        raise HTTPException(status_code=400, detail="Asaas API key não configurada.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


async def tokenize_asaas_card(empresa_id: str, card_data: Dict[str, Any]) -> str:
    """
    Tokeniza os dados do cartão na API do Asaas.
    """
    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    url = (
        "https://sandbox.asaas.com/api/v3/creditCard/tokenize"
        if use_sandbox else
        "https://api.asaas.com/v3/creditCard/tokenize"
    )

    payload = {
        "holderName":  card_data["cardholder_name"],
        "number":      card_data["card_number"],
        "expiryMonth": card_data["expiration_month"],
        "expiryYear":  card_data["expiration_year"],
        "ccv":         card_data["security_code"]
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json().get("creditCardToken")
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} ao tokenizar Asaas: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao tokenizar cartão no Asaas")
        except Exception as e:
            logger.error(f"❌ Erro na tokenização Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro inesperado na tokenização Asaas")


async def list_asaas_pix_keys(empresa_id: str) -> list[Dict[str, Any]]:
    """
    Retorna todas as chaves Pix cadastradas para esta empresa no Asaas.
    Endpoint: GET /v3/pix/addressKeys
    """
    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    base_url = (
        "https://sandbox.asaas.com/api/v3"
        if use_sandbox else
        "https://api.asaas.com/v3"
    )
    url = f"{base_url}/pix/addressKeys"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])


async def create_asaas_payment(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer_data: Dict[str, Any],
    card_data: Optional[Dict[str, Any]] = None,
    card_token: Optional[str] = None,
    installments: int = 1,
    retries: int = 2
) -> Dict[str, Any]:
    """
    Cria um pagamento no Asaas para a empresa específica.
    Suporta PIX e Cartão de Crédito.
    Garante que o cliente exista via get_or_create_asaas_customer.
    """
    # 1) Obtém ou cria cliente na Asaas
    asaas_customer_id = await get_or_create_asaas_customer(
        empresa_id=empresa_id,
        local_customer_id=customer_data.get("local_id", transaction_id),
        customer_data={
            "name":              customer_data.get("name"),
            "email":             customer_data.get("email"),
            "cpfCnpj":           customer_data.get("cpfCnpj") or customer_data.get("cpf"),
            "phone":             customer_data.get("phone"),
            "mobilePhone":       customer_data.get("mobilePhone"),
            "postalCode":        customer_data.get("postalCode"),
            "address":           customer_data.get("address"),
            "addressNumber":     customer_data.get("addressNumber"),
            "externalReference": customer_data.get("externalReference", transaction_id)
        }
    )

    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    base_url = (
        "https://sandbox.asaas.com/api/v3/payments"
        if use_sandbox else
        "https://api.asaas.com/v3/payments"
    )
    callback = creds.get("webhook_pix")

    # 2) Monta payload conforme tipo
    if payment_type == "pix":
        payload = {
            "customer":          asaas_customer_id,
            "value":             amount,
            "billingType":       "PIX",
            "dueDate":           customer_data.get("due_date"),
            "description":       f"PIX {transaction_id}",
            "externalReference": transaction_id,
            "postalService":     False,
            "callbackUrl":       callback
        }
    elif payment_type == "credit_card":
        installments = max(1, min(installments, 12))
        common = {
            "customer":          asaas_customer_id,
            "value":             amount,
            "billingType":       "CREDIT_CARD",
            "dueDate":           customer_data.get("due_date"),
            "description":       f"Cartão {transaction_id}",
            "externalReference": transaction_id,
            "callbackUrl":       callback,
            "installmentCount":  installments
        }
        if card_token:
            payload = {**common, "creditCardToken": card_token}
        else:
            if not card_data:
                raise HTTPException(status_code=400, detail="Dados do cartão obrigatórios.")
            payload = {
                **common,
                "creditCard": card_data,
                "creditCardHolderInfo": {
                    "name":           customer_data.get("name"),
                    "email":          customer_data.get("email"),
                    "cpfCnpj":        customer_data.get("cpfCnpj") or customer_data.get("cpf"),
                    "postalCode":     customer_data.get("postalCode"),
                    "addressNumber":  customer_data.get("addressNumber"),
                    "phone":          customer_data.get("phone")
                }
            }
    else:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido.")

    # 3) Tenta criar pagamento com retries
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(1, retries + 1):
            try:
                resp = await client.post(base_url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP {e.response.status_code} Asaas payment attempt {attempt}: {e.response.text}")
                if e.response.status_code in {400, 402, 403}:
                    raise HTTPException(status_code=e.response.status_code, detail="Erro no pagamento Asaas")
            except Exception as e:
                logger.warning(f"⚠️ Erro conexão Asaas attempt {attempt}: {e}")
            await asyncio.sleep(2)

    raise HTTPException(status_code=500, detail="Falha no pagamento Asaas após múltiplas tentativas")


async def get_asaas_payment_status(empresa_id: str, transaction_id: str) -> Optional[Dict[str, Any]]:
    """
    Verifica o status de um pagamento no Asaas usando externalReference.
    """
    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    base_url = (
        "https://sandbox.asaas.com/api/v3/payments"
        if use_sandbox else
        "https://api.asaas.com/v3/payments"
    )
    url = f"{base_url}?externalReference={transaction_id}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0] if data else None
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro ao buscar status Asaas")


async def create_asaas_refund(empresa_id: str, transaction_id: str) -> Dict[str, Any]:
    """
    Solicita estorno (refund) de um pagamento aprovado na Asaas.
    POST /payments/{transaction_id}/refund
    """
    config = await get_empresa_config(empresa_id) or {}
    api_key = config.get("asaas_api_key")
    if not api_key:
        logger.error(f"❌ Asaas API key não encontrada para refund empresa {empresa_id}")
        raise HTTPException(status_code=400, detail="Asaas API key não configurada para refund.")

    use_sandbox = config.get("use_sandbox", True)
    base_url = (
        "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
    )
    url = f"{base_url}/payments/{transaction_id}/refund"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json"
    }

    logger.info(f"🔄 [create_asaas_refund] solicitando estorno Asaas: POST {url}")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} refund Asaas: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro no estorno Asaas")
        except Exception as e:
            logger.error(f"❌ Erro inesperado refund Asaas: {e!r}")
            raise HTTPException(status_code=500, detail="Erro inesperado no estorno Asaas")

    data = resp.json()
    status = data.get("status", "").lower()
    logger.info(f"✅ [create_asaas_refund] status Asaas para {transaction_id}: {status}")
    return {"status": status, **data}

async def validate_asaas_pix_key(empresa_id: str, chave_pix: str) -> None:
    """
    Lança HTTPException(400) se a chave_pix não estiver cadastrada no Asaas.
    """
    keys = await list_asaas_pix_keys(empresa_id)
    if not any(k.get("key") == chave_pix for k in keys):
        raise HTTPException(
            status_code=400,
            detail=f"Chave Pix '{chave_pix}' não cadastrada no Asaas. Cadastre-a no painel."
        )


async def get_asaas_pix_qr_code(
    empresa_id: str,
    payment_id: str
) -> Dict[str, Any]:
    """
    Busca o QR-Code (base64 + copia e cola) de uma cobrança Pix no Asaas.
    Endpoint: GET /v3/payments/{paymentId}/pixQrCode
    """
    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    base = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
    url = f"{base}/payments/{payment_id}/pixQrCode"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Pix QRCode Asaas HTTP {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=502,
                detail="Erro ao buscar QR-Code Pix no Asaas."
            )

    data = resp.json()
    return {
        "qr_code_base64": data.get("pixQrCodeBase64"),
        "pix_link":       data.get("pixQrCodeCopiado"),
        "expiration":    data.get("expirationDateTime")
    }



__all__ = [
    "tokenize_asaas_card",
    "list_asaas_pix_keys",
    "create_asaas_payment",
    "get_asaas_payment_status",
    "create_asaas_refund",
    "get_or_create_asaas_customer",
    "get_asaas_pix_qr_code",
    "validate_asaas_pix_key",
    "get_asaas_headers",
]
