# payment_kode_api/app/services/gateways/rede_client.py

import asyncio
from base64 import b64encode
from typing import Dict, Any, Optional

import httpx
from fastapi import HTTPException

from payment_kode_api.app.database.database import get_empresa_config
from payment_kode_api.app.services.gateways.payment_payload_mapper import map_to_rede_payload
from payment_kode_api.app.utilities.logging_config import logger

TIMEOUT = 15.0


async def get_rede_headers(empresa_id: str) -> Dict[str, str]:
    """
    Retorna os headers necessários para autenticação na API da Rede.
    """
    config = await get_empresa_config(empresa_id)
    pv = config.get("rede_pv")
    api_key = config.get("rede_api_key")
    if not pv or not api_key:
        raise HTTPException(status_code=401, detail=f"Credenciais da Rede não encontradas para empresa {empresa_id}")

    auth = b64encode(f"{pv}:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }


async def tokenize_rede_card(empresa_id: str, card_data: Dict[str, Any]) -> str:
    """
    Tokeniza os dados do cartão na API da Rede.
    """
    headers = await get_rede_headers(empresa_id)
    url = "https://api.userede.com.br/ecomm/v1/card"
    payload = {
        "number": card_data["card_number"],
        "expirationMonth": card_data["expiration_month"],
        "expirationYear": card_data["expiration_year"],
        "securityCode": card_data["security_code"],
        "holderName": card_data["cardholder_name"]
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
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
    Cria um pagamento na Rede.
    - base_data deve conter todos os campos necessários (transaction_id, amount, installments e dados do cartão).
    - Se 'tokenize' for True e não houver cardToken, tenta tokenizar antes.
    """
    # 1) Mapeia payload genérico para o formato Rede
    payload = map_to_rede_payload(base_data)

    # 2) Ajusta tokenização / card raw
    if "cardToken" in payload:
        # já tokenizado, segue
        pass
    else:
        # payload contém cardNumber, expirationMonth, expirationYear, securityCode, cardHolderName
        if tokenize:
            # gera cardToken e reconstrói payload
            token = await tokenize_rede_card(empresa_id, payload)
            for k in ("cardNumber", "expirationMonth", "expirationYear", "securityCode", "cardHolderName"):
                payload.pop(k, None)
            payload["cardToken"] = token
        else:
            # agrupa em campo 'card'
            card = {
                "number": payload.pop("cardNumber"),
                "expirationMonth": payload.pop("expirationMonth"),
                "expirationYear": payload.pop("expirationYear"),
                "securityCode": payload.pop("securityCode"),
                "holderName": payload.pop("cardHolderName"),
            }
            payload["card"] = card

    # 3) Envia requisição
    headers = await get_rede_headers(empresa_id)
    url = "https://api.userede.com.br/ecomm/v1/transactions"
    logger.info(f"🚀 Enviando pagamento à Rede: empresa={empresa_id} payload={payload!r}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
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


async def create_rede_refund(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None
) -> Dict[str, Any]:
    """
    Solicita estorno de uma transação na Rede.
    - Se `amount` não for informado, estorna o valor total.
    - Se `amount` for um inteiro (em centavos), faz estorno parcial.
    Endpoint: POST /ecomm/v1/transactions/{transaction_id}/refunds
    """
    # 1) Cabeçalhos Basic Auth (PV + API Key)
    headers = await get_rede_headers(empresa_id)

    # 2) Monta URL de estorno
    url = f"https://api.userede.com.br/ecomm/v1/transactions/{transaction_id}/refunds"

    # 3) Payload opcional
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    # 4) Chama a API da Rede
    try:
        logger.info(f"🔄 Solicitando estorno Rede: POST {url} – payload={payload}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        text = e.response.text
        logger.error(f"❌ Rede retornou HTTP {status} no estorno: {text}")
        if status in (400, 402, 403, 404):
            # 400 = requisição inválida, 402 = não autorizado, 403 = proibição, 404 = transação não encontrada
            raise HTTPException(status_code=status, detail=f"Erro no estorno Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao processar estorno")

    except Exception as e:
        logger.error(f"❌ Erro inesperado ao estornar na Rede: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao processar estorno na Rede")