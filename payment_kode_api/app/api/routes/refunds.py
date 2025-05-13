from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

from payment_kode_api.app.database.database import (
    get_payment,
    update_payment_status,
    get_empresa_config
)
from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.services.gateways.sicredi_client import create_sicredi_pix_refund
from payment_kode_api.app.services.gateways.asaas_client import create_asaas_refund
from payment_kode_api.app.services.gateways.rede_client import create_rede_refund
from payment_kode_api.app.services import notify_user_webhook

router = APIRouter()


class PixRefundRequest(BaseModel):
    transaction_id: UUID = Field(..., description="ID da transação Pix a ser estornada")
    amount: Optional[float] = Field(
        None,
        description="Valor a ser estornado (se omitido, devolução total)"
    )



class CreditCardRefundRequest(BaseModel):
    transaction_id: UUID = Field(..., description="ID da transação de cartão a ser estornada")


@router.post("/payment/pix/refund")
async def refund_pix(
    refund_data: PixRefundRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    tx_id      = str(refund_data.transaction_id)
    valor      = refund_data.amount
    logger.info(f"🔖 [refund_pix] iniciar: empresa={empresa_id} transaction_id={tx_id} valor={valor}")

    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")

    # prazo de 7 dias
    created_at = datetime.fromisoformat(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        raise HTTPException(400, "Prazo de estorno expirado: máximo de 7 dias após pagamento")

    txid = payment.get("txid")
    if not txid:
        raise HTTPException(400, "Transação sem txid configurado")

    # provedor primário/segundo
    config    = await get_empresa_config(empresa_id) or {}
    primary   = config.get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"

    for provider in (primary, secondary):
        if provider == "sicredi":
            try:
                resp = await create_sicredi_pix_refund(
                    empresa_id=empresa_id,
                    txid=txid,
                    amount=valor  # <-- passe `amount` e não `valor`
                )
                if resp.get("status", "").upper() == "DEVOLVIDA":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "sicredi",
                            "txid": txid,
                            "payload": resp
                        })
                    return {"status": new_status, "transaction_id": tx_id}
            except HTTPException as he:
                # aborta fallback em 404/400
                if he.status_code in (404, 400):
                    raise
                logger.error(f"❌ [refund_pix] erro Sicredi: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] exceção Sicredi: {e!r}")

        else:  # Asaas
            resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=tx_id)
            if resp2.get("status", "").lower() == "refunded":
                new_status = "canceled"
                await update_payment_status(tx_id, empresa_id, new_status)
                if webhook_url := payment.get("webhook_url"):
                    await notify_user_webhook(webhook_url, {
                        "transaction_id": tx_id,
                        "status": new_status,
                        "provedor": "asaas",
                        "payload": resp2
                    })
                return {"status": new_status, "transaction_id": tx_id}

    raise HTTPException(500, "Falha no estorno via Sicredi e Asaas")



@router.post("/payment/credit-card/refund")
async def refund_credit_card(
    refund_data: CreditCardRefundRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id      = empresa["empresa_id"]
    tx_id           = str(refund_data.transaction_id)
    logger.info(f"🔖 [refund_credit_card] iniciar: empresa={empresa_id} transaction_id={tx_id}")

    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        logger.warning(f"❌ [refund_cc] pagamento não encontrado: {tx_id}")
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    created_at = datetime.fromisoformat(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        logger.error(f"❌ [refund_cc] prazo de estorno expirado para {tx_id}")
        raise HTTPException(status_code=400, detail="Prazo de estorno expirado: máximo de 7 dias após pagamento")

    config = await get_empresa_config(empresa_id) or {}
    primary   = config.get("credit_provider", "rede").lower()
    secondary = "asaas" if primary == "rede" else "rede"
    logger.debug(f"🔧 [refund_cc] provedores: primary={primary}, secondary={secondary}")

    for provider in (primary, secondary):
        if provider == "rede":
            logger.info(f"🚀 [refund_cc] tentando Rede (transaction_id={tx_id})")
            try:
                resp = await create_rede_refund(empresa_id=empresa_id, transaction_id=tx_id)
                # supondo que resp tenha "status": "refunded" ou parecido
                new_status = "canceled"
                await update_payment_status(tx_id, empresa_id, new_status)
                logger.success(f"✅ [refund_cc] Rede refunded: {tx_id}")
                if webhook_url := payment.get("webhook_url"):
                    await notify_user_webhook(webhook_url, {
                        "transaction_id": tx_id,
                        "status": new_status,
                        "provedor": "rede",
                        "payload": resp
                    })
                return {"status": new_status, "transaction_id": tx_id}
            except HTTPException as he:
                if he.status_code in (404, 400):
                    logger.error(f"❌ [refund_cc] abortando por Rede: {he.detail}")
                    raise
                logger.error(f"❌ [refund_cc] erro Rede: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_cc] exceção Rede: {e!r}")

        else:  # asaas
            logger.info(f"⚙️ [refund_cc] tentando Asaas (transaction_id={tx_id})")
            try:
                resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=tx_id)
                status2 = resp2.get("status", "").lower()
                if status2 == "refunded":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.success(f"✅ [refund_cc] Asaas refunded: {tx_id}")
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "asaas",
                            "payload": resp2
                        })
                    return {"status": new_status, "transaction_id": tx_id}
            except Exception as e:
                logger.error(f"❌ [refund_cc] erro Asaas: {e!r}")
                continue

    logger.critical(f"❌ [refund_cc] falha definitiva: {tx_id}")
    raise HTTPException(status_code=500, detail="Falha no estorno via Rede e Asaas")