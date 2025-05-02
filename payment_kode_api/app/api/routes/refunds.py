from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from uuid import UUID

from payment_kode_api.app.database.database import (
    get_payment,
    update_payment_status,
    get_empresa_config,  # <— precisa existir essa função
)
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

    # 1️⃣ Busca pagamento existente
    payment = await get_payment(transaction_id, empresa_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    txid = payment.get("txid")
    if not txid:
        raise HTTPException(status_code=400, detail="Transação sem txid configurado")

    # 2️⃣ Lê a preferência de provider da empresa
    config = await get_empresa_config(empresa_id)
    primary = config.get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"

    # 3️⃣ Tenta na ordem: primary → secondary
    for provider in (primary, secondary):
        if provider == "sicredi":
            try:
                resp = await create_sicredi_pix_refund(empresa_id=empresa_id, txid=txid)
                if resp.get("status", "").upper() == "DEVOLVIDA":
                    new_status = "canceled"
                    await update_payment_status(transaction_id, empresa_id, new_status)
                    if payment.get("webhook_url"):
                        await notify_user_webhook(payment["webhook_url"], {
                            "transaction_id": transaction_id,
                            "status": new_status,
                            "provedor": "sicredi",
                            "txid": txid
                        })
                    return {"status": new_status, "transaction_id": transaction_id}
            except Exception:
                # cai para o próximo provider
                continue

        else:  # provider == "asaas"
            try:
                resp2 = await create_asaas_refund(
                    empresa_id=empresa_id,
                    transaction_id=transaction_id
                )
                if resp2.get("status", "").lower() == "refunded":
                    new_status = "canceled"
                    await update_payment_status(transaction_id, empresa_id, new_status)
                    if payment.get("webhook_url"):
                        await notify_user_webhook(payment["webhook_url"], {
                            "transaction_id": transaction_id,
                            "status": new_status,
                            "provedor": "asaas"
                        })
                    return {"status": new_status, "transaction_id": transaction_id}
            except Exception:
                continue

    # 4️⃣ Se chegou aqui, falhou em ambos
    raise HTTPException(
        status_code=500,
        detail="Falha no estorno via Sicredi e Asaas"
    )
