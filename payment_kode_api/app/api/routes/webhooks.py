from fastapi import APIRouter, HTTPException, Request, Depends
import asyncio
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database import (
    update_payment_status,
    get_empresa_by_chave_pix,
    get_payment
)
from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.services import notify_user_webhook  # ✅ Corrigido aqui

router = APIRouter()


@router.post("/webhook/pix")
async def pix_webhook(request: Request, empresa: dict = Depends(validate_access_token, use_cache=False)):
    """
    Webhook genérico para notificações de pagamentos via Pix.
    Suporta múltiplos players (Sicredi, Rede, Asaas).
    """
    try:
        payload = await request.json()
        logger.info(f"📩 Webhook Pix recebido: {payload}")

        # 🔍 Identifica o provedor pelo payload
        provedor = identificar_provedor(payload)
        logger.info(f"📡 Provedor identificado: {provedor}")

        # 🔹 Se for Sicredi, busca empresa pela chave Pix
        if provedor == "sicredi":
            chave_pix = payload.get("pix", [{}])[0].get("chave")
            if not chave_pix:
                raise HTTPException(status_code=400, detail="Chave Pix ausente no payload.")

            empresa_data = await get_empresa_by_chave_pix(chave_pix)
            if not empresa_data or not empresa_data.get("empresa_id"):
                logger.warning(f"❌ Chave Pix não mapeada no banco: {chave_pix}")
                raise HTTPException(status_code=400, detail="Empresa não encontrada para a chave Pix.")

            empresa_id = empresa_data["empresa_id"]

        else:
            # 🔹 Para outros provedores, usa empresa autenticada
            empresa_id = empresa["empresa_id"]

        # 🔄 Processa em segundo plano
        asyncio.create_task(process_pix_webhook(payload, provedor, empresa_id))

        return {"status": "success", "message": f"Webhook {provedor} recebido com sucesso"}

    except HTTPException as e:
        logger.error(f"Erro HTTP no webhook Pix: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook Pix: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook Pix")


async def process_pix_webhook(payload: dict, provedor: str, empresa_id: str):
    """
    Processa notificações Pix de diferentes provedores em background.
    Atualiza o status do pagamento e dispara o webhook externo.
    """
    try:
        for transaction in payload.get("pix", []):
            transaction_id = transaction.get("txid")
            status = transaction.get("status")

            if not transaction_id or not status:
                logger.warning(f"⚠️ Transação mal formatada: {transaction}")
                continue

            await update_payment_status(transaction_id, empresa_id, status)
            logger.info(f"✅ Pagamento {transaction_id} atualizado para {status} (empresa {empresa_id}, provedor {provedor})")

            # 🔁 Dispara webhook externo se configurado
            payment = await get_payment(transaction_id, empresa_id)
            if payment and payment.get("webhook_url"):
                await notify_user_webhook(payment["webhook_url"], {
                    "transaction_id": transaction_id,
                    "status": status,
                    "provedor": provedor,
                    "payload": transaction
                })

    except Exception as e:
        logger.error(f"❌ Erro no processamento do webhook ({provedor}): {str(e)}")


def identificar_provedor(payload: dict) -> str:
    """
    Identifica o provedor de pagamento com base no payload.
    """
    if "pix" in payload and isinstance(payload["pix"], list):
        return "sicredi"
    if "externalReference" in payload or "reference" in payload:
        return "rede"
    return "asaas"  # fallback padrão
