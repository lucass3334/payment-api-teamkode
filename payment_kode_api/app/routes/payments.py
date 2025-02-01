from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from pydantic.types import StringConstraints, DecimalConstraints
from typing import Annotated, Optional
from ..services import create_asaas_payment, create_sicredi_pix_payment, create_rede_payment
from ..database.database import save_payment, get_payment, update_payment_status
from ..services.config_service import get_empresa_credentials
import uuid
import httpx
from ..utilities.logging_config import logger

router = APIRouter()

# Tipagens para validação
PixKeyType = Annotated[str, StringConstraints(min_length=5, max_length=150)]
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
AmountType = Annotated[float, DecimalConstraints(gt=0, decimal_places=2)]
InstallmentsType = Annotated[int, DecimalConstraints(ge=1, le=12)]
EmpresaIDType = Annotated[str, StringConstraints(min_length=36, max_length=36)]

class PixPaymentRequest(BaseModel):
    empresa_id: EmpresaIDType
    amount: AmountType
    chave_pix: PixKeyType
    txid: TransactionIDType
    transaction_id: Optional[TransactionIDType] = None
    webhook_url: Optional[str] = None

class CreditCardData(BaseModel):
    cardholder_name: Annotated[str, StringConstraints(min_length=3, max_length=50)]
    card_number: Annotated[str, StringConstraints(min_length=13, max_length=19)]
    expiration_month: Annotated[str, StringConstraints(min_length=2, max_length=2)]
    expiration_year: Annotated[str, StringConstraints(min_length=4, max_length=4)]
    security_code: Annotated[str, StringConstraints(min_length=3, max_length=4)]
    soft_descriptor: Optional[Annotated[str, StringConstraints(max_length=13)]] = "Compra Online"

class CreditCardPaymentRequest(BaseModel):
    empresa_id: EmpresaIDType
    amount: AmountType
    transaction_id: Optional[TransactionIDType] = None
    card_data: CreditCardData
    installments: InstallmentsType = 1
    webhook_url: Optional[str] = None

async def notify_user_webhook(webhook_url: str, data: dict):
    """Envia uma notificação para o webhook configurado pelo usuário."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(webhook_url, json=data, timeout=5)
            response.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"Erro ao enviar notificação ao webhook do usuário: {e}")

@router.post("/payment/pix")
async def create_pix_payment(payment_data: PixPaymentRequest, background_tasks: BackgroundTasks):
    """Cria um pagamento via Pix usando o Sicredi para uma empresa específica."""
    transaction_id = payment_data.transaction_id or str(uuid.uuid4())

    existing_payment = get_payment(transaction_id, payment_data.empresa_id)
    if existing_payment:
        return {"status": "already_processed", "message": "Pagamento já foi processado", "transaction_id": transaction_id}

    credentials = get_empresa_credentials(payment_data.empresa_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Empresa não encontrada ou sem credenciais configuradas.")

    save_payment({
        "empresa_id": payment_data.empresa_id,
        "transaction_id": transaction_id,
        "amount": payment_data.amount,
        "payment_type": "pix",
        "status": "pending",
        "webhook_url": payment_data.webhook_url
    })

    try:
        background_tasks.add_task(
            create_sicredi_pix_payment,
            empresa_id=payment_data.empresa_id,
            amount=payment_data.amount,
            chave_pix=payment_data.chave_pix,
            txid=payment_data.txid
        )
        return {"status": "processing", "message": "Pagamento Pix sendo processado", "transaction_id": transaction_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar Pix: {str(e)}")
