# services/gateways/asaas_client.py

import httpx
import asyncio
from fastapi import HTTPException
from typing import Any, Dict, Optional

from ...utilities.logging_config import logger
from ..config_service import get_empresa_credentials
from payment_kode_api.app.database.supabase_client import supabase
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.database.database import get_empresa_config

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
        "holderName":     card_data["cardholder_name"],
        "number":         card_data["card_number"],
        "expiryMonth":    card_data["expiration_month"],
        "expiryYear":     card_data["expiration_year"],
        "ccv":            card_data["security_code"]
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


async def create_asaas_payment(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer: Dict[str, Any],
    card_data: Optional[Dict[str, Any]] = None,
    card_token: Optional[str] = None,
    installments: int = 1,
    retries: int = 2
) -> Dict[str, Any]:
    """
    Cria um pagamento no Asaas para a empresa específica.
    Suporta PIX e Cartão de Crédito.
    """
    headers = await get_asaas_headers(empresa_id)
    creds = await get_empresa_credentials(empresa_id)
    use_sandbox = creds.get("use_sandbox", True)
    base_url = "https://sandbox.asaas.com/api/v3/payments" if use_sandbox else "https://api.asaas.com/v3/payments"
    callback = creds.get("webhook_pix")

    # Monta payload conforme tipo
    if payment_type == "pix":
        payload = {
            "customer":           customer.get("id"),
            "value":              amount,
            "billingType":        "PIX",
            "dueDate":            customer.get("due_date"),
            "description":        f"PIX {transaction_id}",
            "externalReference":  transaction_id,
            "postalService":      False,
            "callbackUrl":        callback
        }
    elif payment_type == "credit_card":
        installments = max(1, min(installments, 12))
        common = {
            "customer":          customer.get("id"),
            "value":             amount,
            "billingType":       "CREDIT_CARD",
            "dueDate":           customer.get("due_date"),
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
                "creditCard": {
                    "holderName":  card_data["cardholder_name"],
                    "number":      card_data["card_number"],
                    "expiryMonth": card_data["expiration_month"],
                    "expiryYear":  card_data["expiration_year"],
                    "ccv":         card_data["security_code"]
                },
                "creditCardHolderInfo": {
                    "name":      card_data["cardholder_name"],
                    "email":     customer.get("email"),
                    "cpfCnpj":   customer.get("document"),
                    "postalCode":customer.get("postal_code"),
                    "addressNumber": customer.get("address_number"),
                    "phone":       customer.get("phone")
                }
            }
    else:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido.")

    # Tenta criar pagamento com retries
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
    base_url = "https://sandbox.asaas.com/api/v3/payments" if use_sandbox else "https://api.asaas.com/v3/payments"
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
    # 1) lê toda a config da empresa de uma vez
    config = await get_empresa_config(empresa_id) or {}
    api_key = config.get("asaas_api_key")
    if not api_key:
        logger.error(f"❌ Asaas API key não encontrada para refund empresa {empresa_id}")
        raise HTTPException(400, "Asaas API key não configurada para refund.")

    use_sandbox = config.get("use_sandbox", True)
    base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
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
            raise HTTPException(e.response.status_code, "Erro no estorno Asaas")
        except Exception as e:
            logger.error(f"❌ Erro inesperado refund Asaas: {e!r}")
            raise HTTPException(500, "Erro inesperado no estorno Asaas")

    data = resp.json()
    status = data.get("status", "").lower()
    logger.info(f"✅ [create_asaas_refund] status Asaas para {transaction_id}: {status}")

    # retorna o payload completo pra onde for manipular
    return {"status": status, **data}


__all__ = [
    "tokenize_asaas_card",
    "create_asaas_payment",
    "get_asaas_payment_status",
    "create_asaas_refund",
]
