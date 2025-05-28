# payment_kode_api/app/services/gateways/rede_client.py

import httpx
from base64 import b64encode
from typing import Any, Dict, Optional

from fastapi import HTTPException

from payment_kode_api.app.core.config import settings
from payment_kode_api.app.database.database import get_empresa_config, get_payment, update_payment_status
from payment_kode_api.app.services.gateways.payment_payload_mapper import map_to_rede_payload
from payment_kode_api.app.utilities.logging_config import logger

TIMEOUT = 15.0

# ─── URL BASE DINÂMICAS ────────────────────────────────────────────────
# 🔧 CORRIGIDO: Usar variável de ambiente do settings
rede_env = getattr(settings, 'REDE_AMBIENT', 'production')
if rede_env.lower() == "sandbox":
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
    **payment_data: Any  # 🔧 MUDANÇA: Usar **kwargs para consistência
) -> Dict[str, Any]:
    """
    Autoriza (e captura, se capture=True) uma transação.
    Endpoint: POST /ecomm/v1/transactions
    """
    # 🔧 CORRIGIDO: Usar payment_data diretamente
    payload = map_to_rede_payload(payment_data)
    tokenize = payment_data.get("tokenize", False)

    # ── Se for tokenização on-the-fly
    if "cardToken" not in payload:
        if tokenize:
            token = await tokenize_rede_card(empresa_id, payload)
            for field in ("cardNumber","expirationMonth","expirationYear","securityCode","cardHolderName"):
                payload.pop(field, None)
            payload["cardToken"] = token
        else:
            # 🔧 CORRIGIDO: Verificar se campos existem antes de fazer pop
            if "cardNumber" in payload:
                payload["card"] = {
                    "number":          payload.pop("cardNumber"),
                    "expirationMonth": payload.pop("expirationMonth"),
                    "expirationYear":  payload.pop("expirationYear"),
                    "securityCode":    payload.pop("securityCode"),
                    "holderName":      payload.pop("cardHolderName"),
                }

    headers = await get_rede_headers(empresa_id)
    logger.info(f"🚀 Enviando pagamento à Rede: empresa={empresa_id}")
    logger.debug(f"📦 Payload Rede: {payload}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TRANSACTIONS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: RESPONSE HANDLING MELHORADO
            return_code = data.get("returnCode", "")
            return_message = data.get("returnMessage", "")
            tid = data.get("tid")
            authorization_code = data.get("authorizationCode")
            
            logger.info(f"📥 Rede response: code={return_code}, message={return_message}, tid={tid}")
            
            # 🔧 NOVO: Atualizar pagamento no banco com dados da Rede
            transaction_id = payment_data.get("transaction_id")
            if transaction_id and return_code == "00":
                # Salvar dados da Rede no banco
                await update_payment_status(
                    transaction_id=transaction_id,
                    empresa_id=empresa_id,
                    status="approved",
                    extra_data={
                        "rede_tid": tid,
                        "authorization_code": authorization_code,
                        "return_code": return_code,
                        "return_message": return_message
                    }
                )
            
            # Retorno estruturado
            if return_code == "00":  # Sucesso
                return {
                    "status": "approved",
                    "transaction_id": transaction_id,
                    "rede_tid": tid,
                    "authorization_code": authorization_code,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }
            else:
                # Pagamento recusado
                logger.warning(f"⚠️ Pagamento Rede recusado: {return_code} - {return_message}")
                return {
                    "status": "failed",
                    "transaction_id": transaction_id,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }

    except httpx.HTTPStatusError as e:
        code, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede retornou HTTP {code}: {text}")
        if code in (400, 402, 403):
            raise HTTPException(status_code=code, detail=f"Pagamento recusado pela Rede: {text}")
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
    🔧 CORRIGIDO: Solicita estorno usando TID da Rede (não nosso transaction_id).
    Endpoint: POST /ecomm/v1/transactions/{rede_tid}/refunds
    """
    # 🔧 NOVO: Buscar TID da Rede no banco
    payment = await get_payment(transaction_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")
    
    rede_tid = payment.get("rede_tid")
    if not rede_tid:
        raise HTTPException(400, "TID da Rede não encontrado para este pagamento")
    
    headers = await get_rede_headers(empresa_id)
    # 🔧 CORRIGIDO: Usar rede_tid ao invés de transaction_id
    url = f"{TRANSACTIONS_URL}/{rede_tid}/refunds"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    try:
        logger.info(f"🔄 Solicitando estorno Rede: POST {url} – payload={payload}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: Verificar código de retorno do estorno
            return_code = data.get("returnCode", "")
            if return_code == "00":
                # Atualizar status no banco
                await update_payment_status(transaction_id, empresa_id, "canceled")
                return {"status": "refunded", **data}
            else:
                raise HTTPException(400, f"Estorno Rede falhou: {data.get('returnMessage')}")

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede estorno HTTP {status}: {text}")
        if status in (400, 402, 403, 404):
            raise HTTPException(status_code=status, detail=f"Erro no estorno Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao processar estorno")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao estornar na Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar estorno na Rede")