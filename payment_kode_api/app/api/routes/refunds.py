from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from uuid import UUID

from payment_kode_api.app.database.database import get_payment, update_payment_status
from payment_kode_api.app.services import (
    create_sicredi_pix_refund,
    create_asaas_refund,
    notify_user_webhook
)
from payment_kode_api.app.security.auth import validate_access_token

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

    # Busca pagamento existente
    payment = await get_payment(transaction_id, empresa_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    txid = payment.get("txid")
    if not txid:
        raise HTTPException(status_code=400, detail="Transação sem txid configurado")

    # 1️⃣ Tenta estorno no Sicredi
    try:
        resp = await create_sicredi_pix_refund(empresa_id=empresa_id, txid=txid)
        # Supondo que Sicredi retorna status "DEVOLVIDA" quando aprovado
        if resp.get("status", "").upper() == "DEVOLVIDA":
            await update_payment_status(transaction_id, empresa_id, "refunded")
            if payment.get("webhook_url"):
                await notify_user_webhook(payment["webhook_url"], {
                    "transaction_id": transaction_id,
                    "status": "refunded",
                    "provedor": "sicredi",
                    "txid": txid
                })
            return {"status": "refunded", "transaction_id": transaction_id}

        raise Exception(f"Estorno Sicredi com status inesperado: {resp.get('status')}")

    except Exception:
        # 2️⃣ Fallback Asaas em caso de erro no Sicredi
        try:
            resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=transaction_id)
            if resp2.get("status", "").lower() == "refunded":
                await update_payment_status(transaction_id, empresa_id, "refunded")
                if payment.get("webhook_url"):
                    await notify_user_webhook(payment["webhook_url"], {
                        "transaction_id": transaction_id,
                        "status": "refunded",
                        "provedor": "asaas"
                    })
                return {"status": "refunded", "transaction_id": transaction_id}
            raise Exception(f"Estorno Asaas falhou: {resp2.get('status')}")

        except Exception:
            raise HTTPException(
                status_code=500,
                detail="Falha no estorno via Sicredi e Asaas"
            )
