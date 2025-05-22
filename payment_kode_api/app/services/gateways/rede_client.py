# payment_kode_api/app/services/gateways/rede_client.py

import httpx
from base64 import b64encode
from typing import Any, Dict, Optional

from fastapi import HTTPException

from payment_kode_api.app.core.config import settings
from payment_kode_api.app.database.database import get_empresa_config
from payment_kode_api.app.services.gateways.payment_payload_mapper import map_to_rede_payload
from payment_kode_api.app.utilities.logging_config import logger

TIMEOUT = 15.0

# ─── URL BASE DINÂMICAS ────────────────────────────────────────────────
if settings.REDE_AMBIENT.lower() == "sandbox":
    ECOMM_BASE_URL = "https://sandbox-erede.useredecloud.com.br/ecomm/v1"
else:
    ECOMM_BASE_URL = "https://api.userede.com.br/ecomm/v1"

CARD_URL         = f"{ECOMM_BASE_URL}/card"
TRANSACTIONS_URL = f"{ECOMM_BASE_URL}/transactions"


async def get_rede_headers(empresa_id: str) -> Dict[str, str]:
    """
    Retorna headers com Basic Auth (PV + Integration Key).
    """
    config = await get_empresa_config(empresa_id)
    pv      = config.get("rede_pv")
    api_key = config.get("rede_api_key")
    if not pv or not api_key:
        raise HTTPException(
            status_code=401,
            detail=f"Credenciais da Rede não encontradas para empresa {empresa_id}"
        )

    auth = b64encode(f"{pv}:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }


async def tokenize_rede_card(empresa_id: str, card_data: Dict[str, Any]) -> str:
    """
    Tokeniza o cartão na Rede.
    Endpoint: POST /ecomm/v1/card
    """
    headers = await get_rede_headers(empresa_id)
    payload = {
        "number":          card_data["card_number"],
        "expirationMonth": card_data["expiration_month"],
        "expirationYear":  card_data["expiration_year"],
        "securityCode":    card_data["security_code"],
        "holderName":      card_data["cardholder_name"],
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(CARD_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json().get("cardToken")
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Rede tokenização HTTP {e.response.status_code}: {e.response.text}")
        raise HTTPException(status_code=502, detail="Erro ao tokenizar cartão na Rede")
    except Exception as e:
        logger.error(f"❌ Rede tokenização erro: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao tokenizar cartão na Rede")


async def create_rede_payment(
    empresa_id: str,
    base_data: Dict[str, Any],
    tokenize: bool = False
) -> Dict[str, Any]:
    """
    Autoriza (e captura, se capture=True) uma transação.
    Endpoint: POST /ecomm/v1/transactions
    """
    payload = map_to_rede_payload(base_data)

    # ── Se for tokenização on-the-fly
    if "cardToken" not in payload:
        if tokenize:
            token = await tokenize_rede_card(empresa_id, payload)
            for field in ("cardNumber","expirationMonth","expirationYear","securityCode","cardHolderName"):
                payload.pop(field, None)
            payload["cardToken"] = token
        else:
            payload["card"] = {
                "number":          payload.pop("cardNumber"),
                "expirationMonth": payload.pop("expirationMonth"),
                "expirationYear":  payload.pop("expirationYear"),
                "securityCode":    payload.pop("securityCode"),
                "holderName":      payload.pop("cardHolderName"),
            }

    headers = await get_rede_headers(empresa_id)
    logger.info(f"🚀 Enviando pagamento à Rede: empresa={empresa_id} payload={payload!r}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TRANSACTIONS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        code, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede retornou HTTP {code}: {text}")
        if code in (400, 402, 403):
            raise HTTPException(status_code=code, detail="Pagamento recusado pela Rede")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão com a Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar pagamento na Rede")


async def capture_rede_transaction(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None
) -> Dict[str, Any]:
    """
    Confirma (captura) uma autorização prévia.
    Endpoint: PUT /ecomm/v1/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.put(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede capture HTTP {status}: {text}")
        if status in (400, 403, 404):
            raise HTTPException(
                status_code=status,
                detail=f"Erro ao capturar transação Rede: {text}"
            )
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao capturar transação")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao capturar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao capturar transação na Rede")


async def get_rede_transaction(
    empresa_id: str,
    transaction_id: str
) -> Dict[str, Any]:
    """
    Consulta o status de uma transação.
    Endpoint: GET /ecomm/v1/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede consulta HTTP {status}: {text}")
        raise HTTPException(status_code=status, detail="Erro ao buscar transação na Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao consultar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao consultar transação na Rede")


async def create_rede_refund(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None
) -> Dict[str, Any]:
    """
    Solicita estorno (total ou parcial).
    Endpoint: POST /ecomm/v1/transactions/{transaction_id}/refunds
    """
    headers = await get_rede_headers(empresa_id)
    url = f"{TRANSACTIONS_URL}/{transaction_id}/refunds"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    try:
        logger.info(f"🔄 Solicitando estorno Rede: POST {url} – payload={payload}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede estorno HTTP {status}: {text}")
        if status in (400, 402, 403, 404):
            raise HTTPException(status_code=status, detail=f"Erro no estorno Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao processar estorno")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao estornar na Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar estorno na Rede")