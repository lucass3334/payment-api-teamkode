from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Optional
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
import httpx
import secrets
from io import BytesIO
import base64
import qrcode
from payment_kode_api.app.database.database import (
    get_empresa_config,
    save_payment,
    get_payment,
    save_tokenized_card,
    get_payment_by_txid,
    update_payment_status_by_txid,
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
from payment_kode_api.app.services import notify_user_webhook
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.security.auth import validate_access_token

router = APIRouter()

# Tipagens para validação
PixKeyType = Annotated[str, Field(min_length=5, max_length=150)]
TransactionIDType = Annotated[UUID, Field()]
InstallmentsType = Annotated[int, Field(ge=1, le=12)]
EmpresaIDType = Annotated[str, Field(min_length=36, max_length=36)]


def generate_txid() -> str:
    """
    Gera um txid válido para o Sicredi:
   - somente caracteres 0–9 e a–f (hex lowercase)
   - comprimento fixo de 32 chars (UUID4.hex), ≤ 35
   """
    # uuid4().hex já retorna 32 caracteres hexadecimais (0-9, a-f)
    return uuid4().hex

class PixPaymentRequest(BaseModel):
    amount: Decimal
    chave_pix: PixKeyType
    txid: Optional[str] = None
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

class SicrediWebhookRequest(BaseModel):
    txid: str
    status: str
    # outros campos podem existir, mas só precisamos de txid e status
@router.post("/webhook/sicredi")
async def sicredi_webhook(
    payload: SicrediWebhookRequest,
):
    """
    Endpoint para receber callbacks de status de cobrança Pix do Sicredi.
    """
    txid = payload.txid
    sicredi_status = payload.status.upper()

    # 1) Busca pagamento pelo txid
    payment = await get_payment_by_txid(txid)
    if not payment:
        raise HTTPException(status_code=404, detail=f"Pagamento não encontrado para txid {txid}")

    empresa_id = payment["empresa_id"]
    transaction_id = payment["transaction_id"]
    webhook_url = payment.get("webhook_url")

    # 2) Mapeia status Sicredi → nosso status
    # Sicredi normalmente retorna 'ATIVA' após criar e 'CONCLUIDA' após pagamento
    if sicredi_status == "CONCLUIDA":
        new_status = "approved"
    elif sicredi_status in ("REMOVIDA_PELO_USUARIO_RECEBEDOR", "REMOVIDA_POR_ERRO"):
        new_status = "canceled"
    else:
        new_status = "failed"

    # 3) Atualiza status no banco
    updated = await update_payment_status_by_txid(
        txid=txid,
        empresa_id=empresa_id,
        status=new_status
    )

    logger.info(f"🔄 Pagamento {transaction_id} (txid={txid}) atualizado para status '{new_status}' via webhook Sicredi")

    # 4) Notifica o cliente via webhook_url, se configurado
    if webhook_url:
        await notify_user_webhook(webhook_url, {
            "transaction_id": transaction_id,
            "status": new_status,
            "provedor": "sicredi",
            "txid": txid
        })

    return {"message": "Webhook Sicredi processado com sucesso"}

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

            if payment_data.webhook_url:
                await notify_user_webhook(payment_data.webhook_url, {
                    "transaction_id": transaction_id,
                    "status": "approved",
                    "provedor": "rede"
                })

            return {"status": "approved", "message": "Pagamento aprovado via Rede", "transaction_id": transaction_id}

        raise Exception("Erro desconhecido na Rede")

    except Exception as e:
        logger.error(f"❌ Erro no gateway Rede para {transaction_id}: {str(e)}")

        try:
            logger.info(f"🔄 Tentando fallback via Asaas para {transaction_id}")
            asaas_payload = map_to_asaas_credit_payload(card_data)
            response = await create_asaas_payment(empresa_id=empresa_id, **asaas_payload)

            if response and response.get("status") == "approved":
                logger.info(f"✅ Pagamento Cartão via Asaas aprovado para {transaction_id}")

                if payment_data.webhook_url:
                    await notify_user_webhook(payment_data.webhook_url, {
                        "transaction_id": transaction_id,
                        "status": "approved",
                        "provedor": "asaas"
                    })

                return {"status": "approved", "message": "Rede falhou, Asaas aprovado", "transaction_id": transaction_id}

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
    txid = payment_data.txid or uuid4().hex  # já é 32 hex chars

    # evita duplicação
    if await get_payment(transaction_id, empresa_id):
        return {"status": "already_processed", "transaction_id": transaction_id}

    # salva o pending
    await save_payment({
        "empresa_id":    empresa_id,
        "transaction_id": transaction_id,
        "amount":         payment_data.amount,
        "payment_type":  "pix",
        "status":        "pending",
        "webhook_url":   payment_data.webhook_url,
        "txid":          txid
    })

    # monta e envia ao Sicredi
    sicredi_payload = map_to_sicredi_payload({**payment_data.dict(), "txid": txid})
    try:
        logger.info(f"🚀 Criando cobrança Pix Sicredi (txid={txid})")
        resp = await create_sicredi_pix_payment(empresa_id=empresa_id, **sicredi_payload)

        # usa sempre o copy‐and‐paste code como pix_link :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
        pix_copy = resp["qr_code"]            # é o data["pixCopiaECola"]
        expires  = resp["expiration"]

        # gera imagem PNG e converte pra base64
        img = qrcode.make(pix_copy)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        qr_png = f"data:image/png;base64,{b64}"

        return {
            "status":          resp["status"].lower(),  # ex: "ativa"
            "transaction_id":  transaction_id,
            "pix_link":        pix_copy,                # agora é o copy‐and‐paste
            "expiration":      expires,
            "qr_code_base64":  qr_png                   # PNG em base64
        }

    except Exception as e:
        logger.error(f"❌ Erro Sicredi txid={txid}: {e!r}")

        # fallback Asaas
        logger.warning(f"⚠️ Fallback Asaas txid={txid}")
        asaas_payload = {"amount": float(payment_data.amount), "chave_pix": payment_data.chave_pix, "txid": txid}
        resp = await create_asaas_payment(empresa_id=empresa_id, **asaas_payload)
        if resp.get("status") == "approved":
            return {
                "status":         resp["status"].lower(),
                "transaction_id": transaction_id,
                "pix_link":       resp.get("pixKey"),
                "qr_code_base64": resp.get("qrCode"),         # se Asaas retornar já em base64
                "expiration":     resp.get("expirationDateTime")
            }

        raise HTTPException(
            status_code=500,
            detail="Falha no pagamento via Sicredi e Asaas"
        )
