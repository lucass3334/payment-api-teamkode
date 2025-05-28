from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

from payment_kode_api.app.database.database import (
    get_payment,
    update_payment_status,
    get_empresa_config
)
from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.services.gateways.sicredi_client import create_sicredi_pix_refund
from payment_kode_api.app.services.gateways.asaas_client import create_asaas_refund
from payment_kode_api.app.services.gateways.rede_client import create_rede_refund
from payment_kode_api.app.services import notify_user_webhook

router = APIRouter()


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
    )  # 🔧 NOVO: Campo amount para estornos parciais


@router.post("/payment/pix/refund")
async def refund_pix(
    refund_data: PixRefundRequest,
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    tx_id      = str(refund_data.transaction_id)
    valor      = refund_data.amount
    logger.info(f"🔖 [refund_pix] iniciar: empresa={empresa_id} transaction_id={tx_id} valor={valor}")

    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")

    # 🔧 MELHORADO: Verificar se o pagamento foi aprovado
    if payment.get("status") != "approved":
        raise HTTPException(400, f"Não é possível estornar pagamento com status: {payment.get('status')}")

    # prazo de 7 dias
    created_at = datetime.fromisoformat(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        raise HTTPException(400, "Prazo de estorno expirado: máximo de 7 dias após pagamento")

    txid = payment.get("txid")
    if not txid:
        raise HTTPException(400, "Transação sem txid configurado")

    # provedor primário/secundário
    config    = await get_empresa_config(empresa_id) or {}
    primary   = config.get("pix_provider", "sicredi").lower()
    secondary = "asaas" if primary == "sicredi" else "sicredi"
    
    logger.info(f"🔧 [refund_pix] provedores: primary={primary}, secondary={secondary}")

    for provider in (primary, secondary):
        if provider == "sicredi":
            try:
                logger.info(f"🚀 [refund_pix] tentando Sicredi (txid={txid})")
                resp = await create_sicredi_pix_refund(
                    empresa_id=empresa_id,
                    txid=txid,
                    amount=valor  # valor pode ser None para estorno total
                )
                
                # 🔧 MELHORADO: Verificar diferentes status de sucesso
                status_upper = resp.get("status", "").upper()
                if status_upper in ("DEVOLVIDA", "REMOVIDA_PELO_USUARIO_RECEBEDOR"):
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_pix] Sicredi estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "sicredi",
                            "txid": txid,
                            "payload": resp
                        })
                    return {"status": new_status, "transaction_id": tx_id, "provider": "sicredi"}
                    
            except HTTPException as he:
                # aborta fallback em 404/400
                if he.status_code in (404, 400):
                    logger.error(f"❌ [refund_pix] abortando por Sicredi: {he.detail}")
                    raise
                logger.error(f"❌ [refund_pix] erro Sicredi: {he.detail}")
            except Exception as e:
                logger.error(f"❌ [refund_pix] exceção Sicredi: {e!r}")

        else:  # Asaas
            try:
                logger.info(f"⚙️ [refund_pix] tentando Asaas (transaction_id={tx_id})")
                resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=tx_id)
                
                if resp2.get("status", "").lower() == "refunded":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_pix] Asaas estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
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
    empresa: dict = Depends(validate_access_token)
):
    empresa_id = empresa["empresa_id"]
    tx_id      = str(refund_data.transaction_id)
    amount     = refund_data.amount  # 🔧 NOVO: Suporte a estorno parcial
    
    logger.info(f"🔖 [refund_credit_card] iniciar: empresa={empresa_id} transaction_id={tx_id} amount={amount}")

    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        logger.warning(f"❌ [refund_cc] pagamento não encontrado: {tx_id}")
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    # 🔧 MELHORADO: Verificar se o pagamento foi aprovado
    if payment.get("status") != "approved":
        raise HTTPException(400, f"Não é possível estornar pagamento com status: {payment.get('status')}")

    created_at = datetime.fromisoformat(payment["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(days=7):
        logger.error(f"❌ [refund_cc] prazo de estorno expirado para {tx_id}")
        raise HTTPException(status_code=400, detail="Prazo de estorno expirado: máximo de 7 dias após pagamento")

    config = await get_empresa_config(empresa_id) or {}
    primary   = config.get("credit_provider", "rede").lower()
    secondary = "asaas" if primary == "rede" else "rede"
    logger.debug(f"🔧 [refund_cc] provedores: primary={primary}, secondary={secondary}")

    for provider in (primary, secondary):
        if provider == "rede":
            logger.info(f"🚀 [refund_cc] tentando Rede (transaction_id={tx_id})")
            try:
                # 🔧 CORRIGIDO: create_rede_refund já busca o rede_tid internamente
                resp = await create_rede_refund(
                    empresa_id=empresa_id, 
                    transaction_id=tx_id,
                    amount=int(amount * 100) if amount else None  # 🔧 NOVO: Converter para centavos
                )
                
                # 🔧 MELHORADO: Verificar diferentes status de sucesso
                if resp.get("status") == "refunded" or resp.get("returnCode") == "00":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_cc] Rede estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
                            "transaction_id": tx_id,
                            "status": new_status,
                            "provedor": "rede",
                            "rede_tid": payment.get("rede_tid"),  # 🔧 NOVO: Incluir TID da Rede
                            "payload": resp
                        })
                    return {
                        "status": new_status, 
                        "transaction_id": tx_id, 
                        "provider": "rede",
                        "rede_tid": payment.get("rede_tid")  # 🔧 NOVO
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

        else:  # asaas
            logger.info(f"⚙️ [refund_cc] tentando Asaas (transaction_id={tx_id})")
            try:
                resp2 = await create_asaas_refund(empresa_id=empresa_id, transaction_id=tx_id)
                status2 = resp2.get("status", "").lower()
                
                if status2 == "refunded":
                    new_status = "canceled"
                    await update_payment_status(tx_id, empresa_id, new_status)
                    logger.info(f"✅ [refund_cc] Asaas estornado: {tx_id}")
                    
                    if webhook_url := payment.get("webhook_url"):
                        await notify_user_webhook(webhook_url, {
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


# 🔧 NOVO: Endpoint para consultar status de estorno
@router.get("/payment/{transaction_id}/refund-status")
async def get_refund_status(
    transaction_id: UUID,
    empresa: dict = Depends(validate_access_token)
):
    """
    Consulta o status atual de um pagamento para verificar se foi estornado.
    """
    empresa_id = empresa["empresa_id"]
    tx_id = str(transaction_id)
    
    payment = await get_payment(tx_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")
    
    return {
        "transaction_id": tx_id,
        "status": payment.get("status"),
        "can_refund": (
            payment.get("status") == "approved" and 
            datetime.now(timezone.utc) - datetime.fromisoformat(payment["created_at"]) <= timedelta(days=7)
        ),
        "created_at": payment.get("created_at"),
        "payment_type": payment.get("payment_type"),
        "amount": payment.get("amount"),
        "rede_tid": payment.get("rede_tid"),  # Para debug/suporte
        "txid": payment.get("txid")  # Para debug/suporte
    }