from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from typing import Annotated, Optional
import uuid
import httpx

from payment_kode_api.app.services.gateways.asaas_client import create_asaas_payment
from payment_kode_api.app.services.gateways.sicredi_client import create_sicredi_pix_payment
from payment_kode_api.app.services.gateways.rede_client import create_rede_payment
from payment_kode_api.app.services.gateways.payment_payload_mapper import (
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload
)
from payment_kode_api.app.security.crypto import decrypt_card_data  # 🔹 Importação da função de descriptografia
from payment_kode_api.app.database.database import save_payment, get_payment
from payment_kode_api.app.services.config_service import get_empresa_credentials
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.security.auth import validate_access_token  # 🔹 Validação de access_token

router = APIRouter()

# Tipagens para validação
PixKeyType = Annotated[str, Field(min_length=5, max_length=150)]
TransactionIDType = Annotated[str, Field(min_length=6, max_length=35)]
AmountType = Annotated[float, Field(gt=0, decimal_places=2)]
InstallmentsType = Annotated[int, Field(ge=1, le=12)]
EmpresaIDType = Annotated[str, Field(min_length=36, max_length=36)]

class PixPaymentRequest(BaseModel):
    amount: AmountType
    chave_pix: PixKeyType
    txid: TransactionIDType
    transaction_id: Optional[TransactionIDType] = None
    webhook_url: Optional[str] = None

class CreditCardPaymentRequest(BaseModel):
    amount: AmountType
    encrypted_card_data: str  # 🔹 Agora os dados do cartão devem ser enviados criptografados
    installments: InstallmentsType
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

@router.post("/payment/credit-card")
async def create_credit_card_payment(
    payment_data: CreditCardPaymentRequest, 
    background_tasks: BackgroundTasks, 
    empresa: dict = Depends(validate_access_token)  # 🔹 Valida o access_token
):
    """Cria um pagamento via Cartão de Crédito usando Rede como principal e Asaas como fallback."""
    empresa_id = empresa["empresa_id"]
    transaction_id = payment_data.transaction_id or str(uuid.uuid4())

    existing_payment = await get_payment(transaction_id, empresa_id)
    if existing_payment:
        return {"status": "already_processed", "message": "Pagamento já foi processado", "transaction_id": transaction_id}

    credentials = get_empresa_credentials(empresa_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Empresa não encontrada ou sem credenciais configuradas.")

    try:
        # 🔹 Descriptografa os dados do cartão antes de prosseguir
        card_data = decrypt_card_data(empresa_id, payment_data.encrypted_card_data)

    except Exception as e:
        logger.error(f"❌ Erro ao descriptografar os dados do cartão: {str(e)}")
        raise HTTPException(status_code=400, detail="Erro ao processar dados do cartão.")

    await save_payment({
        "empresa_id": empresa_id,
        "transaction_id": transaction_id,
        "amount": payment_data.amount,
        "payment_type": "credit_card",
        "status": "pending",
        "webhook_url": payment_data.webhook_url
    })

    # 🔹 Mapeia os dados para o formato correto antes de enviar para a Rede
    rede_payload = map_to_rede_payload({**payment_data.dict(), **card_data})

    try:
        logger.info(f"🚀 Tentando processar pagamento Cartão via Rede para {transaction_id}")
        response = await create_rede_payment(empresa_id=empresa_id, **rede_payload)

        if response and response.get("status") == "approved":
            logger.info(f"✅ Pagamento Cartão via Rede aprovado para {transaction_id}")
            return {"status": "approved", "message": "Pagamento aprovado via Rede", "transaction_id": transaction_id}

        logger.warning(f"⚠️ Pagamento via Rede falhou para {transaction_id}. Tentando fallback via Asaas.")
        raise Exception("Erro desconhecido na Rede")

    except Exception as e:
        logger.error(f"❌ Erro no gateway Rede para {transaction_id}: {str(e)}")

        try:
            logger.info(f"🔄 Tentando fallback via Asaas para {transaction_id}")
            asaas_payload = map_to_asaas_credit_payload({**payment_data.dict(), **card_data})
            response = await create_asaas_payment(empresa_id=empresa_id, **asaas_payload)

            if response and response.get("status") == "approved":
                logger.info(f"✅ Pagamento Cartão via Asaas aprovado para {transaction_id}")
                return {"status": "approved", "message": "Rede falhou, usando Asaas como fallback", "transaction_id": transaction_id}

            raise HTTPException(status_code=500, detail="Falha no pagamento via Rede e Asaas")

        except Exception as fallback_error:
            logger.error(f"❌ Erro no fallback via Asaas para {transaction_id}: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail="Falha no pagamento via Rede e Asaas")
