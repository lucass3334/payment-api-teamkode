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
from payment_kode_api.app.services import (
    create_sicredi_pix_refund,
    create_asaas_refund,
    notify_user_webhook
)

router = APIRouter()

class PixRefundRequest(BaseModel):
    transaction_id: UUID = Field(..., description="ID da transação a ser estornada")

@router.post("/payment/pix/refund")
async def refund_pix(
    refund_data: PixRefundRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    tx_id = str(refund_data.transaction_id)
    logger.info(f"🔖 [refund_pix] iniciar: empresa={empresa_id} transaction_id={tx_id}")

    # 1) Busca pagamento
    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        logger.warning(f"❌ [refund_pix] pagamento não encontrado: {tx_id}")
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    # 1.1) Verifica prazo de estorno: máximo de 7 dias após o pagamento
    created_at = datetime.fromisoformat(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        logger.error(f"❌ [refund_pix] prazo de estorno expirado para {tx_id}")
        raise HTTPException(status_code=400, detail="Prazo de estorno expirado: máximo de 7 dias após pagamento")

    txid = payment.get("txid")
    if not txid:
        logger.error(f"❌ [refund_pix] txid não configurado: {tx_id}")
        raise HTTPException(status_code=400, detail="Transação sem txid configurado")

    # 2) Orquestra provedores
    config = await get_empresa_config(empresa_id) or {}
    primary = config.get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"
    logger.debug(f"🔧 [refund_pix] provedores: primary={primary}, secondary={secondary}")

    # 3) Tenta estorno em cada provedor
    for provider in (primary, secondary):
        if provider == "sicredi":
            logger.info(f"🚀 [refund_pix] tentando Sicredi (txid={txid})")
            try:
                resp = await create_sicredi_pix_refund(empresa_id=empresa_id, txid=txid)
                status_ret = resp.get("status", "").upper()
                logger.debug(f"📥 [refund_pix] Sicredi status: {status_ret}")
                if status_ret == "DEVOLVIDA":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.success(f"✅ [refund_pix] Sicredi devolvida: {tx_id}")
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
                # aborta fallback se 404 (não existe) ou 400 (prazo expirado)
                if he.status_code in (404, 400):
                    logger.error(f"❌ [refund_pix] abortando por Sicredi: {he.detail}")
                    raise
                logger.error(f"❌ [refund_pix] erro Sicredi: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] exceção Sicredi: {e!r}")

        else:
            logger.info(f"⚙️ [refund_pix] tentando Asaas (tx_id={tx_id})")
            try:
                resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=tx_id)
                status2 = resp2.get("status", "").lower()
                logger.debug(f"📥 [refund_pix] Asaas status: {status2}")
                if status2 == "refunded":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.success(f"✅ [refund_pix] Asaas refunded: {tx_id}")
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "asaas",
                            "payload": resp2
                        })
                    return {"status": new_status, "transaction_id": tx_id}
            except Exception as e:
                logger.error(f"❌ [refund_pix] erro Asaas: {e!r}")
                continue

    # 4) falha geral
    logger.critical(f"❌ [refund_pix] falha definitiva: {tx_id}")
    raise HTTPException(status_code=500, detail="Falha no estorno via Sicredi e Asaas")