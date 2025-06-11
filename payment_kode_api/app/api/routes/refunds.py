# payment_kode_api/app/api/routes/refunds.py

import re
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

# ✅ NOVO: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    PaymentRepositoryInterface,
    ConfigRepositoryInterface,
    WebhookServiceInterface,
    SicrediGatewayInterface,
    AsaasGatewayInterface,
    RedeGatewayInterface,
)

# ✅ NOVO: Dependency injection
from ...dependencies import (
    get_payment_repository,
    get_config_repository,
    get_webhook_service,
    get_sicredi_gateway,
    get_asaas_gateway,
    get_rede_gateway,
)

from payment_kode_api.app.security.auth import validate_access_token

router = APIRouter()


def safe_parse_datetime(date_string: str) -> datetime:
    """
    🔧 FUNÇÃO AUXILIAR: Parse seguro de datetime com diferentes formatos.
    
    Resolve problemas com:
    - Microsegundos com diferentes números de dígitos
    - Diferentes formatos de timezone
    - Strings mal formatadas
    """
    if not date_string:
        raise ValueError("Data string vazia")
    
    try:
        # Primeiro, tentar o formato padrão
        return datetime.fromisoformat(date_string)
    except ValueError:
        pass
    
    try:
        # 🔧 CORREÇÃO: Normalizar microsegundos para 6 dígitos
        # Padrão: YYYY-MM-DDTHH:MM:SS.microsegundos+timezone
        pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{1,6})([+-]\d{2}:\d{2})'
        match = re.match(pattern, date_string)
        
        if match:
            base_datetime = match.group(1)
            microseconds = match.group(2)
            timezone_part = match.group(3)
            
            # Normalizar microsegundos para 6 dígitos
            if len(microseconds) < 6:
                microseconds = microseconds.ljust(6, '0')
            elif len(microseconds) > 6:
                microseconds = microseconds[:6]
            
            # Reconstituir a string
            normalized_string = f"{base_datetime}.{microseconds}{timezone_part}"
            return datetime.fromisoformat(normalized_string)
            
    except Exception:
        pass
    
    try:
        # 🔧 FALLBACK: Tentar outros formatos comuns
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
        ]
        
        for fmt in formats_to_try:
            try:
                # Remover timezone se formato não suporta
                test_string = date_string
                if '%z' not in fmt and 'Z' not in fmt:
                    test_string = re.sub(r'[+-]\d{2}:\d{2}|Z$', '', date_string)
                
                parsed = datetime.strptime(test_string, fmt)
                
                # Adicionar timezone UTC se não presente
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                
                return parsed
                
            except ValueError:
                continue
                
    except Exception:
        pass
    
    # 🚨 ÚLTIMO RECURSO: Retornar datetime atual com warning
    logger.warning(f"⚠️ Não foi possível parsear data '{date_string}', usando datetime atual")
    return datetime.now(timezone.utc)


class PixRefundRequest(BaseModel):
    transaction_id: UUID = Field(..., description="ID da transação Pix a ser estornada")
    amount: Optional[float] = Field(
        None,
        description="Valor a ser estornado (se omitido, devolução total)"
    )


class CreditCardRefundRequest(BaseModel):
    transaction_id: UUID = Field(..., description="ID da transação de cartão a ser estornada")
    amount: Optional[float] = Field(
        None,
        description="Valor a ser estornado em centavos (se omitido, estorno total)"
    )


@router.post("/payment/pix/refund")
async def refund_pix(
    refund_data: PixRefundRequest,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection das interfaces
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository),
    config_repo: ConfigRepositoryInterface = Depends(get_config_repository),
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service),
    sicredi_gateway: SicrediGatewayInterface = Depends(get_sicredi_gateway),
    asaas_gateway: AsaasGatewayInterface = Depends(get_asaas_gateway)
):
    empresa_id = empresa["empresa_id"]
    tx_id = str(refund_data.transaction_id)
    valor = refund_data.amount
    
    logger.info(f"🔖 [refund_pix] iniciar: empresa={empresa_id} transaction_id={tx_id} valor={valor}")

    # ✅ USANDO INTERFACE
    payment = await payment_repo.get_payment(tx_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")

    # 🔧 MELHORADO: Verificar se o pagamento foi aprovado
    if payment.get("status") != "approved":
        raise HTTPException(400, f"Não é possível estornar pagamento com status: {payment.get('status')}")

    # 🔧 CORRIGIDO: Usar parse seguro de data
    created_at = safe_parse_datetime(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        raise HTTPException(400, "Prazo de estorno expirado: máximo de 7 dias após pagamento")

    txid = payment.get("txid")
    if not txid:
        raise HTTPException(400, "Transação sem txid configurado")

    # ✅ USANDO INTERFACE: Provedor primário/secundário
    config = await config_repo.get_empresa_config(empresa_id) or {}
    primary = config.get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"
    
    logger.info(f"🔧 [refund_pix] provedores: primary={primary}, secondary={secondary}")

    for provider in (primary, secondary):
        if provider == "sicredi":
            try:
                logger.info(f"🚀 [refund_pix] tentando Sicredi (txid={txid})")
                # ✅ USANDO INTERFACE
                resp = await sicredi_gateway.create_pix_refund(
                    empresa_id=empresa_id,
                    txid=txid,
                    amount=valor
                )
                
                # 🔧 MELHORADO: Verificar diferentes status de sucesso
                status_upper = resp.get("status", "").upper()
                if status_upper in ("DEVOLVIDA", "REMOVIDA_PELO_USUARIO_RECEBEDOR"):
                    new_status = "canceled"
                    # ✅ USANDO INTERFACE
                    await payment_repo.update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_pix] Sicredi estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        # ✅ USANDO INTERFACE
                        await webhook_service.notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "sicredi",
                            "txid": txid,
                            "payload": resp
                        })
                    return {"status": new_status, "transaction_id": tx_id, "provider": "sicredi"}
                    
            except HTTPException as he:
                # Aborta fallback em 404/400
                if he.status_code in (404, 400):
                    logger.error(f"❌ [refund_pix] abortando por Sicredi: {he.detail}")
                    raise
                logger.error(f"❌ [refund_pix] erro Sicredi: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] exceção Sicredi: {e!r}")

        else:  # Asaas
            try:
                logger.info(f"⚙️ [refund_pix] tentando Asaas (transaction_id={tx_id})")
                # ✅ USANDO INTERFACE
                resp2 = await asaas_gateway.create_refund(empresa_id=empresa_id, transaction_id=tx_id)
                
                if resp2.get("status", "").lower() == "refunded":
                    new_status = "canceled"
                    # ✅ USANDO INTERFACE
                    await payment_repo.update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_pix] Asaas estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        # ✅ USANDO INTERFACE
                        await webhook_service.notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "asaas",
                            "payload": resp2
                        })
                    return {"status": new_status, "transaction_id": tx_id, "provider": "asaas"}
                    
            except Exception as e:
                logger.error(f"❌ [refund_pix] erro Asaas: {e!r}")

    raise HTTPException(500, "Falha no estorno via Sicredi e Asaas")


@router.post("/payment/credit-card/refund")
async def refund_credit_card(
    refund_data: CreditCardRefundRequest,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection das interfaces
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository),
    config_repo: ConfigRepositoryInterface = Depends(get_config_repository),
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service),
    rede_gateway: RedeGatewayInterface = Depends(get_rede_gateway),
    asaas_gateway: AsaasGatewayInterface = Depends(get_asaas_gateway)
):
    empresa_id = empresa["empresa_id"]
    tx_id = str(refund_data.transaction_id)
    amount = refund_data.amount
    
    logger.info(f"🔖 [refund_credit_card] iniciar: empresa={empresa_id} transaction_id={tx_id} amount={amount}")

    # ✅ USANDO INTERFACE
    payment = await payment_repo.get_payment(tx_id, empresa_id)
    if not payment:
        logger.warning(f"❌ [refund_cc] pagamento não encontrado: {tx_id}")
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    # 🔧 MELHORADO: Verificar se o pagamento foi aprovado
    if payment.get("status") != "approved":
        raise HTTPException(400, f"Não é possível estornar pagamento com status: {payment.get('status')}")

    # 🔧 CORRIGIDO: Usar parse seguro de data
    created_at = safe_parse_datetime(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        logger.error(f"❌ [refund_cc] prazo de estorno expirado para {tx_id}")
        raise HTTPException(status_code=400, detail="Prazo de estorno expirado: máximo de 7 dias após pagamento")

    # ✅ USANDO INTERFACE
    config = await config_repo.get_empresa_config(empresa_id) or {}
    primary = config.get("credit_provider", "rede").lower()
    secondary = "asaas" if primary == "rede" else "rede"
    logger.debug(f"🔧 [refund_cc] provedores: primary={primary}, secondary={secondary}")

    for provider in (primary, secondary):
        if provider == "rede":
            logger.info(f"🚀 [refund_cc] tentando Rede (transaction_id={tx_id})")
            try:
                # ✅ USANDO INTERFACE
                resp = await rede_gateway.create_refund(
                    empresa_id=empresa_id, 
                    transaction_id=tx_id,
                    amount=int(amount * 100) if amount else None
                )
                
                # 🔧 MELHORADO: Verificar diferentes status de sucesso
                if resp.get("status") == "refunded" or resp.get("returnCode") in ["00","359", "360"]:
                    new_status = "canceled"
                    # ✅ USANDO INTERFACE
                    await payment_repo.update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_cc] Rede estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        # ✅ USANDO INTERFACE
                        await webhook_service.notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "rede",
                            "rede_tid": payment.get("rede_tid"),
                            "payload": resp
                        })
                    return {
                        "status": new_status, 
                        "transaction_id": tx_id, 
                        "provider": "rede",
                        "rede_tid": payment.get("rede_tid"),
                        "return_code": resp.get("return_code"),
                        "message": resp.get("message", "Estorno processado com sucesso")
                    } 
                else:
                    logger.warning(f"⚠️ [refund_cc] Rede retornou status inesperado: {resp}")
                    
            except HTTPException as he:
                if he.status_code in (404, 400):
                    logger.error(f"❌ [refund_cc] abortando por Rede: {he.detail}")
                    raise
                logger.error(f"❌ [refund_cc] erro Rede: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_cc] exceção Rede: {e!r}")

        else:  # Asaas
            logger.info(f"⚙️ [refund_cc] tentando Asaas (transaction_id={tx_id})")
            try:
                # ✅ USANDO INTERFACE
                resp2 = await asaas_gateway.create_refund(empresa_id=empresa_id, transaction_id=tx_id)
                status2 = resp2.get("status", "").lower()
                
                if status2 == "refunded":
                    new_status = "canceled"
                    # ✅ USANDO INTERFACE
                    await payment_repo.update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_cc] Asaas estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        # ✅ USANDO INTERFACE
                        await webhook_service.notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "asaas",
                            "payload": resp2
                        })
                    return {"status": new_status, "transaction_id": tx_id, "provider": "asaas"}
                    
            except Exception as e:
                logger.error(f"❌ [refund_cc] erro Asaas: {e!r}")

    logger.error(f"❌ [refund_cc] falha definitiva: {tx_id}")
    raise HTTPException(status_code=500, detail="Falha no estorno via Rede e Asaas")


@router.get("/payment/{transaction_id}/refund-status")
async def get_refund_status(
    transaction_id: UUID,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository)
):
    """
    Consulta o status atual de um pagamento para verificar se foi estornado.
    """
    empresa_id = empresa["empresa_id"]
    tx_id = str(transaction_id)
    
    # ✅ USANDO INTERFACE
    payment = await payment_repo.get_payment(tx_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")
    
    return {
        "transaction_id": tx_id,
        "status": payment.get("status"),
        "can_refund": (
            payment.get("status") == "approved" and 
            datetime.now(timezone.utc) - safe_parse_datetime(payment["created_at"]) <= timedelta(days=7)
        ),
        "created_at": payment.get("created_at"),
        "payment_type": payment.get("payment_type"),
        "amount": payment.get("amount"),
        "rede_tid": payment.get("rede_tid"),
        "txid": payment.get("txid")
    }