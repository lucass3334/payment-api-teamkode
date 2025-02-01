from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from ..services import create_asaas_payment, create_sicredi_pix_payment, create_rede_payment
from ..database.database import save_payment, get_payment, update_payment_status
from ..services.config_service import get_empresa_credentials
import uuid
import httpx
from ..utilities.logging_config import logger

router = APIRouter()

# Tipagens para validação
PixKeyType = Annotated[str, Field(min_length=5, max_length=150)]
TransactionIDType = Annotated[str, Field(min_length=6, max_length=35)]
AmountType = Annotated[float, Field(gt=0, decimal_places=2)]
InstallmentsType = Annotated[int, Field(ge=1, le=12)]
EmpresaIDType = Annotated[str, Field(min_length=36, max_length=36)]

class PixPaymentRequest(BaseModel):
    empresa_id: EmpresaIDType
    amount: AmountType
    chave_pix: PixKeyType
    txid: TransactionIDType
    transaction_id: Optional[TransactionIDType] = None
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
    """Cria um pagamento via Pix usando Sicredi como primeira opção e Asaas como fallback."""
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
        logger.info(f"Tentando processar pagamento Pix via Sicredi para {transaction_id}")
        response = await create_sicredi_pix_payment(
            empresa_id=payment_data.empresa_id,
            amount=payment_data.amount,
            chave_pix=payment_data.chave_pix,
            txid=payment_data.txid
        )
        if response and response.get("status") == "pending":
            logger.info(f"Pagamento Pix via Sicredi iniciado com sucesso para {transaction_id}")
            return {"status": "processing", "message": "Pagamento Pix sendo processado via Sicredi", "transaction_id": transaction_id}

        logger.warning(f"Pagamento via Sicredi não foi iniciado corretamente para {transaction_id}. Tentando fallback via Asaas.")
        raise Exception("Erro desconhecido no Sicredi")

    except Exception as e:
        logger.error(f"Erro no Sicredi para {transaction_id}: {str(e)}")

        try:
            logger.info(f"Sicredi falhou, tentando fallback via Asaas para {transaction_id}")
            response = await create_asaas_payment(
                empresa_id=payment_data.empresa_id,
                amount=payment_data.amount,
                payment_type="pix",
                transaction_id=transaction_id,
                customer={}
            )
            if response and response.get("status") == "pending":
                logger.info(f"Pagamento Pix via Asaas iniciado com sucesso para {transaction_id}")
                return {"status": "processing", "message": "Sicredi falhou, usando Asaas como fallback", "transaction_id": transaction_id}
            
            logger.error(f"Erro no Asaas, pagamento falhou para {transaction_id}")
            raise HTTPException(status_code=500, detail="Falha no pagamento Pix em todos os gateways disponíveis")

        except Exception as fallback_error:
            logger.error(f"Erro no fallback via Asaas para {transaction_id}: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail="Falha no pagamento Pix em todos os gateways disponíveis")
