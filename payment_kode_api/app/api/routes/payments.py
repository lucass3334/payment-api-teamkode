from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
import httpx
import secrets
from io import BytesIO
import base64
import qrcode
import asyncio
from datetime import datetime, timedelta, timezone
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.database.supabase_client import supabase
from payment_kode_api.app.database.database import (
    get_empresa_config,
    save_payment,
    get_payment,
    save_tokenized_card,
    get_payment_by_txid,
    update_payment_status_by_txid,
    get_tokenized_card,
    get_sicredi_token_or_refresh,
    update_payment_status
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
from payment_kode_api.app.core.config import settings
from ...services.config_service import load_certificates_from_bucket
from payment_kode_api.app.utilities.cert_utils import build_ssl_context_from_memory

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
    background_tasks: BackgroundTasks,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    transaction_id = str(payment_data.transaction_id or uuid4())
    # normaliza TXID para uppercase (evita mismatch)
    txid = (payment_data.txid or uuid4().hex).upper()

    logger.info(f"🔖 [create_pix_payment] iniciar: empresa={empresa_id} txid={txid} transaction_id={transaction_id}")

    # evita duplicação
    if await get_payment(transaction_id, empresa_id):
        logger.warning(f"⚠️ [create_pix_payment] já processado: transaction_id={transaction_id}")
        return {"status": "already_processed", "transaction_id": transaction_id}

    # salva como pending
    await save_payment({
        "empresa_id":     empresa_id,
        "transaction_id": transaction_id,
        "amount":         payment_data.amount,
        "payment_type":   "pix",
        "status":         "pending",
        "webhook_url":    payment_data.webhook_url,
        "txid":           txid
    })
    logger.debug(f"💾 [create_pix_payment] payment registrado como pending no DB")

    # payload pra Sicredi
    sicredi_payload = map_to_sicredi_payload({**payment_data.dict(), "txid": txid})
    try:
        logger.info(f"🚀 [create_pix_payment] criando cobrança Sicredi (txid={txid}) payload={sicredi_payload!r}")
        resp = await create_sicredi_pix_payment(empresa_id=empresa_id, **sicredi_payload)
        logger.debug(f"✅ [create_pix_payment] Sicredi respondeu: {resp!r}")

        # extrai sempre o QR-code "pixCopiaECola"
        qr = resp["qr_code"]
        # o link de pagamento (se quiser expor)
        link = resp["pix_link"]
        # data de vencimento (quando agendada) ou None
        due_date = resp.get("due_date")
        # prazo limite para estorno
        refund_deadline = resp["refund_deadline"]
        # em cobrança imediata vem expiration
        expiration = resp.get("expiration")

        # gera PNG + base64
        img = qrcode.make(qr)
        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_png = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

        # agenda polling
        if payment_data.webhook_url:
            logger.info(f"🏷️ [create_pix_payment] agendando polling para txid={txid}")
            background_tasks.add_task(
                _poll_sicredi_status,
                txid,
                empresa_id,
                transaction_id,
                payment_data.webhook_url
            )

        # monta o retorno
        result = {
            "status":           resp["status"].lower(),
            "transaction_id":   transaction_id,
            "pix_link":         link,
            "qr_code_base64":   qr_png,
            "refund_deadline":  refund_deadline
        }
        if expiration is not None:
            result["expiration"] = expiration
        if due_date:
            result["due_date"] = due_date

        return result

    except Exception as e:
        logger.error(f"❌ [create_pix_payment] erro Sicredi txid={txid}: {e!r}")

        # fallback Asaas
        logger.warning(f"⚠️ [create_pix_payment] fallback Asaas txid={txid}")
        resp2 = await create_asaas_payment(
            empresa_id=empresa_id,
            amount=float(payment_data.amount),
            payment_type="pix",
            transaction_id=transaction_id,
            customer={
                "id": settings.ASAAS_DEFAULT_CUSTOMER,
                "due_date": datetime.now(timezone.utc).date().isoformat()
            },
        )
        logger.debug(f"💬 [create_pix_payment] Asaas response: {resp2!r}")
        if resp2.get("status") == "approved":
            logger.info(f"✅ [create_pix_payment] Asaas approved for {transaction_id}")
            return {
                "status":         resp2["status"].lower(),
                "transaction_id": transaction_id,
                "pix_link":       resp2.get("pixKey"),
                "qr_code_base64": resp2.get("qrCode"),
                "expiration":     resp2.get("expirationDateTime")
            }

        logger.critical(f"❌ [create_pix_payment] falha definitiva {transaction_id}")
        raise HTTPException(500, "Falha no pagamento via Sicredi e Asaas")


async def _poll_sicredi_status(
    txid: str,
    empresa_id: str,
    transaction_id: str,
    webhook_url: str
):
    logger.info(f"🔄 [_poll_sicredi_status] iniciar: txid={txid} transaction_id={transaction_id}")
    start = datetime.now(timezone.utc)
    deadline = start + timedelta(minutes=15)
    interval = 5

    # carrega certs e monta SSLContext
    certs = await load_certificates_from_bucket(empresa_id)
    ssl_ctx = build_ssl_context_from_memory(
        cert_pem=certs["cert_path"],
        key_pem=certs["key_path"],
        ca_pem=certs.get("ca_path")
    )
    logger.debug(f"🔐 [_poll_sicredi_status] SSL context pronto para empresa {empresa_id}")

    # mapeamento de status Sicredi → status internos
    status_map = {
        "concluida": "approved",
        "removida_pelo_usuario_recebedor": "canceled",
        # Se precisar de mais mapeamentos, adicione aqui
    }

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=10.0) as client:
        while datetime.now(timezone.utc) < deadline:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.debug(f"⏱️ [_poll] elapsed={elapsed:.1f}s, interval={interval}s")

            token = await get_sicredi_token_or_refresh(empresa_id)
            logger.debug(f"🔑 [_poll] token (prefixo): {token[:10]}...")

            # consulta v3 usando txid (já em uppercase)
            url = f"{settings.SICREDI_API_URL}/api/v3/cob/{txid}"
            logger.debug(f"📡 [_poll] GET {url}")
            res = await client.get(url, headers={"Authorization": f"Bearer {token}"})

            if res.status_code == 404:
                logger.info(f"❓ [_poll] cobrança não encontrada (404), aguardando próximo loop")
                await asyncio.sleep(interval)
                continue

            logger.debug(f"📥 [_poll] HTTP {res.status_code} → {res.text}")
            res.raise_for_status()

            data = res.json()
            sicredi_status = data.get("status", "").lower()
            logger.info(f"🔍 [_poll] status Sicredi txid={txid} → {sicredi_status}")

            # se for final (não ativa nem pendente), aplica o mapeamento e encerra
            if sicredi_status not in {"ativa", "pendente"}:
                mapped_status = status_map.get(sicredi_status, sicredi_status)
                logger.info(f"✅ [_poll] status final detectado ({sicredi_status}), mapeado para ({mapped_status}), atualizando DB e notificando")

                await update_payment_status(transaction_id, empresa_id, mapped_status)
                await notify_user_webhook(webhook_url, {
                    "transaction_id": transaction_id,
                    "status": mapped_status,
                    "provedor": "sicredi",
                    "payload": data
                })
                return

            # após 2min, aumento o intervalo
            if elapsed > 120:
                interval = 10

            await asyncio.sleep(interval)

    logger.error(f"❌ [_poll] deadline atingida sem status final txid={txid}")

