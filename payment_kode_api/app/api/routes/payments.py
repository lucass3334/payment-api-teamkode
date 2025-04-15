from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Optional
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
import httpx

from payment_kode_api.app.database.database import (
    get_empresa_config,
    save_payment,
    get_payment,
    save_tokenized_card,
    get_tokenized_card
)
from payment_kode_api.app.services.gateways.asaas_client import create_asaas_payment
from payment_kode_api.app.services.gateways.sicredi_client import create_sicredi_pix_payment
from payment_kode_api.app.services.gateways.rede_client import create_rede_payment
from payment_kode_api.app.services.gateways.payment_payload_mapper import (
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload
)
from payment_kode_api.app.services.config_service import get_empresa_credentials
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.security.auth import validate_access_token

router = APIRouter()

# Tipagens para validação
PixKeyType = Annotated[str, Field(min_length=5, max_length=150)]
TransactionIDType = Annotated[UUID, Field()]
InstallmentsType = Annotated[int, Field(ge=1, le=12)]
EmpresaIDType = Annotated[str, Field(min_length=36, max_length=36)]


class PixPaymentRequest(BaseModel):
    amount: Decimal
    chave_pix: PixKeyType
    txid: str
    transaction_id: Optional[TransactionIDType] = None
    webhook_url: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, v):
        try:
            decimal_value = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if decimal_value <= 0:
                raise ValueError("O valor de 'amount' deve ser maior que 0.")
            return decimal_value
        except Exception as e:
            raise ValueError(f"Valor inválido para amount: {v}. Erro: {e}")


class TokenizeCardRequest(BaseModel):
    customer_id: str
    card_number: str
    expiration_month: str
    expiration_year: str
    security_code: str
    cardholder_name: str


class CreditCardPaymentRequest(BaseModel):
    amount: Decimal
    card_token: Optional[str] = None
    card_data: Optional[TokenizeCardRequest] = None
    installments: InstallmentsType
    transaction_id: Optional[TransactionIDType] = None
    webhook_url: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, v):
        try:
            decimal_value = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if decimal_value <= 0:
                raise ValueError("O valor de 'amount' deve ser maior que 0.")
            return decimal_value
        except Exception as e:
            raise ValueError(f"Valor inválido para amount: {v}. Erro: {e}")


async def notify_user_webhook(webhook_url: str, data: dict):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(webhook_url, json=data, timeout=5)
            response.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"Erro ao enviar notificação ao webhook do usuário: {e}")


@router.post("/payment/tokenize-card")
async def tokenize_card(
    card_data: TokenizeCardRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    card_token = str(uuid4())
    encrypted_card_data = str(card_data.dict())

    await save_tokenized_card({
        "empresa_id": empresa_id,
        "customer_id": card_data.customer_id,
        "card_token": card_token,
        "encrypted_card_data": encrypted_card_data
    })

    return {"card_token": card_token}


@router.post("/payment/credit-card")
async def create_credit_card_payment(
    payment_data: CreditCardPaymentRequest,
    background_tasks: BackgroundTasks,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    transaction_id = str(payment_data.transaction_id or uuid4())

    existing_payment = await get_payment(transaction_id, empresa_id)
    if existing_payment:
        return {"status": "already_processed", "message": "Pagamento já foi processado", "transaction_id": transaction_id}

    credentials = await get_empresa_config(empresa_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Empresa não encontrada ou sem credenciais configuradas.")

    if payment_data.card_token:
        card_data = await get_tokenized_card(payment_data.card_token)
        if not card_data:
            raise HTTPException(status_code=400, detail="Cartão não encontrado ou expirado.")
    elif payment_data.card_data:
        card_data = payment_data.card_data.dict()
        token_response = await tokenize_card(payment_data.card_data, empresa)
        card_data["card_token"] = token_response["card_token"]
    else:
        raise HTTPException(status_code=400, detail="É necessário fornecer um `card_token` ou `card_data`.")

    await save_payment({
        "empresa_id": empresa_id,
        "transaction_id": transaction_id,
        "amount": payment_data.amount,
        "payment_type": "credit_card",
        "status": "pending",
        "webhook_url": payment_data.webhook_url
    })

    rede_payload = map_to_rede_payload(card_data)

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
            asaas_payload = map_to_asaas_credit_payload(card_data)
            response = await create_asaas_payment(empresa_id=empresa_id, **asaas_payload)

            if response and response.get("status") == "approved":
                logger.info(f"✅ Pagamento Cartão via Asaas aprovado para {transaction_id}")
                return {"status": "approved", "message": "Rede falhou, usando Asaas como fallback", "transaction_id": transaction_id}

            raise HTTPException(status_code=500, detail="Falha no pagamento via Rede e Asaas")

        except Exception as fallback_error:
            logger.error(f"❌ Erro no fallback via Asaas para {transaction_id}: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail="Falha no pagamento via Rede e Asaas")


@router.post("/payment/pix")
async def create_pix_payment(
    payment_data: PixPaymentRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    transaction_id = str(payment_data.transaction_id or uuid4())

    existing_payment = await get_payment(transaction_id, empresa_id)
    if existing_payment:
        return {"status": "already_processed", "message": "Pagamento já foi processado", "transaction_id": transaction_id}

    credentials = await get_empresa_config(empresa_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Empresa não encontrada ou sem credenciais configuradas.")

    await save_payment({
        "empresa_id": empresa_id,
        "transaction_id": transaction_id,
        "amount": payment_data.amount,
        "payment_type": "pix",
        "status": "pending",
        "webhook_url": payment_data.webhook_url
    })

    sicredi_payload = map_to_sicredi_payload(payment_data.dict())

    try:
        logger.info(f"🚀 Tentando processar pagamento Pix via Sicredi para {transaction_id}")
        response = await create_sicredi_pix_payment(empresa_id=empresa_id, **sicredi_payload)

        if response and response.get("status") == "approved":
            logger.info(f"✅ Pagamento Pix via Sicredi aprovado para {transaction_id}")
            return {"status": "approved", "message": "Pagamento aprovado via Sicredi", "transaction_id": transaction_id}

        logger.warning(f"⚠️ Pagamento via Sicredi falhou para {transaction_id}. Tentando fallback via Asaas.")
        raise Exception("Erro desconhecido no Sicredi")

    except Exception as e:
        logger.error(f"❌ Erro no gateway Sicredi para {transaction_id}: {str(e)}")

        try:
            logger.info(f"🔄 Tentando fallback via Asaas para {transaction_id}")
            asaas_payload = map_to_asaas_pix_payload(payment_data.dict())
            response = await create_asaas_payment(empresa_id=empresa_id, **asaas_payload)

            if response and response.get("status") == "approved":
                logger.info(f"✅ Pagamento Pix via Asaas aprovado para {transaction_id}")
                return {"status": "approved", "message": "Sicredi falhou, usando Asaas como fallback", "transaction_id": transaction_id}

            raise HTTPException(status_code=500, detail="Falha no pagamento via Sicredi e Asaas")

        except Exception as fallback_error:
            logger.error(f"❌ Erro no fallback via Asaas para {transaction_id}: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail="Falha no pagamento via Sicredi e Asaas")
