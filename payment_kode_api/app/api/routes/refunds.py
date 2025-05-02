# refunds.py

from typing import Dict, Any, Optional
from uuid import UUID
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
    transaction_id = str(refund_data.transaction_id)
    logger.info(f"🔄 [refund_pix] iniciar: empresa={empresa_id} transaction_id={transaction_id}")

    # 1) Recupera o pagamento no DB
    payment = await get_payment(transaction_id, empresa_id)
    if not payment:
        logger.warning(f"⚠️ [refund_pix] pagamento não encontrado: {transaction_id}")
        raise HTTPException(404, "Pagamento não encontrado")

    txid = payment.get("txid")
    if not txid:
        logger.error(f"❌ [refund_pix] txid não configurado: {transaction_id}")
        raise HTTPException(400, "Transação sem txid configurado")

    # 2) Decide ordem de provedores via empresas_config
    config: Optional[Dict[str, Any]] = await get_empresa_config(empresa_id)
    primary = (config or {}).get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"
    logger.debug(f"🔧 [refund_pix] ordem provedores: primary={primary}, secondary={secondary}")

    # 3) Tenta estornar em cada provedor
    for provider in (primary, secondary):
        if provider == "sicredi":
            logger.info(f"🚀 [refund_pix] tentando estorno no Sicredi (txid={txid})")
            try:
                resp = await create_sicredi_pix_refund(empresa_id=empresa_id, txid=txid)
                logger.debug(f"📥 [refund_pix] resposta Sicredi: {resp!r}")

                if resp.get("status", "").upper() == "DEVOLVIDA":
                    await update_payment_status(transaction_id, empresa_id, "canceled")
                    logger.info(f"✅ [refund_pix] Sicredi devolvida: {transaction_id}")
                    if payment.get("webhook_url"):
                        await notify_user_webhook(payment["webhook_url"], {
                            "transaction_id": transaction_id,
                            "status": "canceled",
                            "provedor": "sicredi",
                            "txid": txid
                        })
                    return {"status": "canceled", "transaction_id": transaction_id}

                logger.error(f"❌ [refund_pix] Sicredi retornou status inesperado: {resp.get('status')}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] erro Sicredi: {e!r}")
                # passa para o próximo provedor
                continue

        else:  # Asaas
            logger.info(f"⚙️ [refund_pix] tentando estorno no Asaas (transaction_id={transaction_id})")
            try:
                resp2 = await create_asaas_refund(
                    empresa_id=empresa_id,
                    transaction_id=transaction_id
                )
                logger.debug(f"📥 [refund_pix] resposta Asaas: {resp2!r}")

                if resp2.get("status", "").lower() == "refunded":
                    await update_payment_status(transaction_id, empresa_id, "canceled")
                    logger.info(f"✅ [refund_pix] Asaas refunded: {transaction_id}")
                    if payment.get("webhook_url"):
                        await notify_user_webhook(payment["webhook_url"], {
                            "transaction_id": transaction_id,
                            "status": "canceled",
                            "provedor": "asaas"
                        })
                    return {"status": "canceled", "transaction_id": transaction_id}

                logger.error(f"❌ [refund_pix] Asaas retornou status inesperado: {resp2.get('status')}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] erro Asaas: {e!r}")
                continue

    # 4) Se nenhum provedor obteve sucesso
    logger.critical(f"❌ [refund_pix] falha definitiva: {transaction_id}")
    raise HTTPException(status_code=500, detail="Falha no estorno via Sicredi e Asaas")
