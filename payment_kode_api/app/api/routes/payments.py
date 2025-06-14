from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Annotated, Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
from datetime import date, datetime, timedelta, timezone
import httpx
import secrets
from io import BytesIO
import base64
import qrcode
import asyncio

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
    update_payment_status,
)
# pega o helper do cliente Asaas direto do módulo de banco
from payment_kode_api.app.database.customers import get_asaas_customer
from payment_kode_api.app.services.gateways.asaas_client import (
    create_asaas_payment,
    get_asaas_payment_status,
    get_asaas_pix_qr_code,
    validate_asaas_pix_key,
)
from payment_kode_api.app.services.gateways.sicredi_client import create_sicredi_pix_payment
from payment_kode_api.app.services.gateways.rede_client import create_rede_payment
from payment_kode_api.app.services.gateways.payment_payload_mapper import (
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload,
)
from payment_kode_api.app.services import notify_user_webhook
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.utilities.cert_utils import build_ssl_context_from_memory
from ...services.config_service import load_certificates_from_bucket


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
    due_date: Optional[date] = None

    # NOVOS CAMPOS
    nome_devedor: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[EmailStr] = None  # incluído para cadastro no Asaas

    data_marketing: Optional[Dict[str, Any]] = Field(default=None, description="Dados extras de marketing, serão armazenados e retornados no webhook")

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
    empresa_id     = empresa["empresa_id"]
    transaction_id = str(payment_data.transaction_id or uuid4())

    # evita duplicação
    if await get_payment(transaction_id, empresa_id):
        return {
            "status": "already_processed",
            "message": "Pagamento já processado",
            "transaction_id": transaction_id
        }

    # qual gateway usar?
    config = await get_empresa_config(empresa_id)
    credit_provider = (config or {}).get("credit_provider", "rede").lower()
    logger.info(f"🔍 Provider de crédito: {credit_provider} para empresa {empresa_id}")

    # recupera ou gera token interno
    if payment_data.card_token:
        card_data = await get_tokenized_card(payment_data.card_token)
        if not card_data:
            raise HTTPException(400, "Cartão não encontrado ou expirado.")
    elif payment_data.card_data:
        token_resp = await tokenize_card(payment_data.card_data, empresa)
        card_data  = {**payment_data.card_data.dict(), "card_token": token_resp["card_token"]}
    else:
        raise HTTPException(400, "É necessário fornecer `card_token` ou `card_data`.")

    # salva como pending
    await save_payment({
        "empresa_id":     empresa_id,
        "transaction_id": transaction_id,
        "amount":         payment_data.amount,
        "payment_type":   "credit_card",
        "status":         "pending",
        "webhook_url":    payment_data.webhook_url
    })

    # prepara dados para o mapper
    base_data   = {**payment_data.dict(exclude_unset=False), "transaction_id": transaction_id}
    mapper_data = {**base_data, **card_data}

    # ——— Rede ———
    if credit_provider == "rede":
        try:
            logger.info(f"🚀 Processando pagamento via Rede: tx={transaction_id}")
            
            # 🔧 CORRIGIDO: Usar **kwargs ao invés de base_data
            resp = await create_rede_payment(
                empresa_id=empresa_id,
                **mapper_data  # 🔧 MUDANÇA: **kwargs para consistência
            )
            
            logger.info(f"📥 Resposta Rede: {resp}")
            
            # 🔧 CORRIGIDO: Verificar status adequadamente
            if resp.get("status") == "approved":
                # Pagamento aprovado - notificar via webhook
                if payment_data.webhook_url:
                    background_tasks.add_task(
                        notify_user_webhook,
                        payment_data.webhook_url,
                        {
                            "transaction_id": transaction_id, 
                            "status": "approved", 
                            "provedor": "rede",
                            "rede_tid": resp.get("rede_tid"),
                            "authorization_code": resp.get("authorization_code")
                        }
                    )
                return {
                    "status": "approved", 
                    "message": "Pagamento aprovado via Rede", 
                    "transaction_id": transaction_id,
                    "rede_tid": resp.get("rede_tid"),
                    "authorization_code": resp.get("authorization_code")
                }
            elif resp.get("status") == "failed":
                # Pagamento recusado
                return {
                    "status": "failed",
                    "message": f"Pagamento recusado pela Rede: {resp.get('return_message')}",
                    "transaction_id": transaction_id,
                    "return_code": resp.get("return_code")
                }
            else:
                # Status inesperado
                logger.warning(f"⚠️ Status inesperado da Rede: {resp}")
                raise HTTPException(502, "Resposta inesperada do gateway Rede")
                
        except HTTPException:
            raise  # repassa erros 4xx/5xx gerados pelo client
        except Exception as e:
            logger.error(f"❌ Erro inesperado com Rede: {e}")
            raise HTTPException(502, "Erro no gateway Rede.")

    # ——— Asaas ———
    elif credit_provider == "asaas":
        asaas_info = map_to_asaas_credit_payload(mapper_data)
        customer_data = {
            "local_id":          transaction_id,
            "name":              mapper_data["cardholder_name"],
            "email":             mapper_data.get("email") or mapper_data.get("customer_email"),
            "cpfCnpj":           mapper_data.get("cpf") or mapper_data.get("cnpj"),
            "phone":             mapper_data.get("phone"),
            "externalReference": transaction_id
        }
        try:
            logger.info(f"🚀 Processando pagamento via Asaas: tx={transaction_id}")
            resp = await create_asaas_payment(
                empresa_id=empresa_id,
                amount=asaas_info["value"],
                payment_type="credit_card",
                transaction_id=transaction_id,
                customer_data=customer_data,
                card_token=asaas_info.get("creditCardToken"),
                card_data=asaas_info.get("creditCard"),
                installments=asaas_info.get("installmentCount", 1),
            )
        except Exception as e:
            logger.error(f"❌ Erro Asaas: {e}")
            raise HTTPException(502, "Erro no gateway Asaas.")

        if resp.get("status", "").lower() == "approved":
            if payment_data.webhook_url:
                background_tasks.add_task(
                    notify_user_webhook,
                    payment_data.webhook_url,
                    {"transaction_id": transaction_id, "status": "approved", "provedor": "asaas"}
                )
            return {"status": "approved", "message": "Pagamento aprovado via Asaas", "transaction_id": transaction_id}

        raise HTTPException(402, "Pagamento recusado pela Asaas.")

    # ——— Provedor inválido ———
    else:
        raise HTTPException(400, f"Provedor de crédito desconhecido: {credit_provider}")



@router.post("/payment/pix")
async def create_pix_payment(
    payment_data: PixPaymentRequest,
    background_tasks: BackgroundTasks,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id     = empresa["empresa_id"]
    transaction_id = str(payment_data.transaction_id or uuid4())
    txid           = (payment_data.txid or uuid4().hex).upper()

    logger.info(f"🔖 [create_pix_payment] iniciar: empresa={empresa_id} txid={txid} transaction_id={transaction_id}")

    # Validação para cobranças com vencimento
    if payment_data.due_date:
        if not payment_data.nome_devedor:
            raise HTTPException(status_code=400, detail="Para cobrança com vencimento, 'nome_devedor' é obrigatório.")
        if not (payment_data.cpf or payment_data.cnpj):
            raise HTTPException(status_code=400, detail="Para cobrança com vencimento, 'cpf' ou 'cnpj' é obrigatório.")

    # Evita duplicação
    if await get_payment(transaction_id, empresa_id):
        logger.warning(f"⚠️ [create_pix_payment] já processado: transaction_id={transaction_id}")
        return {"status": "already_processed", "transaction_id": transaction_id}

    # Salva como pending
    await save_payment({
        "empresa_id":     empresa_id,
        "transaction_id": transaction_id,
        "amount":         payment_data.amount,
        "payment_type":   "pix",
        "status":         "pending",
        "webhook_url":    payment_data.webhook_url,
        "txid":           txid,
        "data_marketing": payment_data.data_marketing
    })
    logger.debug("💾 [create_pix_payment] payment registrado como pending no DB")

    # Determina provider de PIX
    config       = await get_empresa_config(empresa_id)
    pix_provider = config.get("pix_provider", "sicredi").lower()
    logger.info(f"🔍 [create_pix_payment] pix_provider configurado: {pix_provider}")

    if pix_provider == "sicredi":
        # ——— Fluxo Sicredi ———
        sicredi_payload = map_to_sicredi_payload({
            **payment_data.dict(exclude_unset=False),
            "txid":     txid,
            "due_date": payment_data.due_date.isoformat() if payment_data.due_date else None
        })
        logger.debug(f"📦 [create_pix_payment] payload Sicredi: {sicredi_payload!r}")

        resp = await create_sicredi_pix_payment(empresa_id=empresa_id, **sicredi_payload)
        logger.debug(f"✅ [create_pix_payment] Sicredi respondeu: {resp!r}")

        qr_copy = resp["qr_code"]
        img     = qrcode.make(qr_copy)
        buf     = BytesIO()
        img.save(buf, format="PNG")
        qr_png  = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

        if payment_data.webhook_url:
            background_tasks.add_task(
                _poll_sicredi_status,
                txid, empresa_id, transaction_id, payment_data.webhook_url
            )

        result = {
            "status":          resp["status"].lower(),
            "transaction_id":  transaction_id,
            "pix_link":        qr_copy,
            "qr_code_base64":  qr_png,
            "refund_deadline": resp["refund_deadline"]
        }
        if resp.get("expiration") is not None:
            result["expiration"] = resp["expiration"]
        if resp.get("due_date"):
            result["due_date"] = resp["due_date"]

        return result

    elif pix_provider == "asaas":
        # ——— Fluxo Asaas ———
        if not payment_data.chave_pix:
            raise HTTPException(status_code=400, detail="Para Pix via Asaas, 'chave_pix' é obrigatório.")

        # Valida se a chave já está cadastrada
        await validate_asaas_pix_key(empresa_id, payment_data.chave_pix)

        # Monta payload simples de Pix
        pix_payload = map_to_asaas_pix_payload({
            **payment_data.dict(exclude_unset=False),
            "txid": txid
        })

        # Monta customer_data e injeta a pixKey
        customer_data = {
            "local_id":          transaction_id,
            "name":              payment_data.nome_devedor or "",
            "email":             payment_data.email,
            "cpfCnpj":           payment_data.cpf or payment_data.cnpj,
            "externalReference": transaction_id,
            "due_date":          (payment_data.due_date or datetime.now(timezone.utc).date()).isoformat(),
            "pixKey":            payment_data.chave_pix
        }

        logger.info(f"🚀 [create_pix_payment] criando cobrança Asaas para txid={txid}")
        resp2 = await create_asaas_payment(
            empresa_id=empresa_id,
            amount=float(payment_data.amount),
            payment_type="pix",
            transaction_id=transaction_id,
            customer_data=customer_data
        )
        logger.debug(f"💬 [create_pix_payment] Asaas respondeu: {resp2!r}")

        if resp2.get("status", "").lower() != "approved":
            logger.critical(f"❌ [create_pix_payment] erro Asaas {transaction_id}: {resp2}")
            raise HTTPException(status_code=500, detail="Falha no pagamento via Asaas")

        # --> Polling do QR Code
        max_retries = 5
        Interval = 2
        qr_info = {"qr_code_base64":None}
        for _ in range(max_retries):
            qr_info = await get_asaas_pix_qr_code(empresa_id, resp2["id"])
            if qr_info["qr_code_base64"]:
                break
            await asyncio.sleep(Interval)
            Interval *= 2

        return {
            "status":           resp2["status"].lower(),
            "transaction_id":   transaction_id,
            "pix_link":         qr_info["pix_link"],
            "qr_code_base64":   qr_info["qr_code_base64"],
            "expiration":       qr_info.get("expiration")
        }

    else:
        # Provedor desconhecido
        logger.error(f"❌ [create_pix_payment] provedor PIX desconhecido: {pix_provider}")
        raise HTTPException(status_code=400, detail=f"Provedor PIX desconhecido: {pix_provider}")


async def _poll_sicredi_status(
    txid: str,
    empresa_id: str,
    transaction_id: str,
    webhook_url: str
):
    """
    Polling de status de cobrança Pix Sicredi.
    Tenta em paralelo /api/v3/cob/{txid} e /api/v2/cobv/{txid},
    até encontrar um status final ou expirar o prazo de 15 minutos.
    """
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

    status_map = {
        "concluida": "approved",
        "removida_pelo_usuario_recebedor": "canceled",
        "removida_por_erro": "canceled",
    }

    base   = settings.SICREDI_API_URL
    url_v3 = f"{base}/api/v3/cob/{txid}"
    url_v2 = f"{base}/api/v2/cobv/{txid}"

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=10.0) as client:
        while datetime.now(timezone.utc) < deadline:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.debug(f"⏱️ [_poll] elapsed={elapsed:.1f}s, interval={interval}s")

            token = await get_sicredi_token_or_refresh(empresa_id)
            headers = {"Authorization": f"Bearer {token}"}

            results = await asyncio.gather(
                client.get(url_v3, headers=headers),
                client.get(url_v2, headers=headers),
                return_exceptions=True
            )

            any_found = False
            for res in results:
                if isinstance(res, Exception) or res.status_code == 404:
                    continue
                any_found = True
                try:
                    res.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error(f"❌ [_poll] HTTP {e.response.status_code}: {e.response.text}")
                    continue

                data = res.json()
                status_raw = data.get("status", "").lower()
                logger.info(f"🔍 [_poll] status Sicredi txid={txid} → {status_raw}")

                if status_raw not in {"ativa", "pendente"}:
                    mapped = status_map.get(status_raw, status_raw)
                    await update_payment_status(transaction_id, empresa_id, mapped)

                    # recupera data_marketing e notifica
                    payment   = await get_payment(transaction_id, empresa_id)
                    marketing = payment.get("data_marketing") if payment else None

                    await notify_user_webhook(webhook_url, {
                        "transaction_id":  transaction_id,
                        "status":          mapped,
                        "provedor":        "sicredi",
                        "payload":         data,
                        "data_marketing":  marketing
                    })
                    return

            if not any_found:
                logger.info("❓ [_poll] nenhuma cobrança encontrada, aguardando próximo loop")

            if elapsed > 120:
                interval = 10
            await asyncio.sleep(interval)

    logger.error(f"❌ [_poll] deadline atingida sem status final txid={txid}")


async def _poll_asaas_pix_status(
    transaction_id: str,
    empresa_id: str,
    webhook_url: str,
    interval: int = 5,
    timeout_minutes: int = 15
):
    """
    Polling de status de uma cobrança PIX via Asaas.
    Consulta GET /payments?externalReference={transaction_id} até encontrar status final
    (RECEIVED -> approved, REFUNDED -> canceled) ou expirar o prazo.
    """
    start    = datetime.now(timezone.utc)
    deadline = start + timedelta(minutes=timeout_minutes)

    while datetime.now(timezone.utc) < deadline:
        data = await get_asaas_payment_status(empresa_id, transaction_id)
        if data:
            status_raw = data.get("status", "").upper()
            if status_raw in {"RECEIVED", "CONFIRMED"}:
                mapped = "approved"
            elif status_raw in {"REFUNDED", "REFUNDED_PARTIAL"}:
                mapped = "canceled"
            else:
                mapped = None

            if mapped:
                await update_payment_status(transaction_id, empresa_id, mapped)

                # recupera data_marketing e notifica
                payment   = await get_payment(transaction_id, empresa_id)
                marketing = payment.get("data_marketing") if payment else None

                if webhook_url:
                    await notify_user_webhook(webhook_url, {
                        "transaction_id":  transaction_id,
                        "status":          mapped,
                        "provedor":        "asaas",
                        "payload":         data,
                        "data_marketing":  marketing
                    })
                return

        await asyncio.sleep(interval)

    logger.error(f"❌ [_poll_asaas_pix_status] deadline atingida sem status final txid={transaction_id}")