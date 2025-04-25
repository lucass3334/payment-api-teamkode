from fastapi import APIRouter, HTTPException, Request
import asyncio
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database.database import (
    get_empresa_by_chave_pix,
    get_payment,
    update_payment_status
)
from payment_kode_api.app.services import notify_user_webhook

router = APIRouter()

@router.post("/webhook/pix")
async def pix_webhook(request: Request):
    """
    Webhook genérico para notificações de pagamentos via Pix.
    Suporta múltiplos provedores: Sicredi, Rede e Asaas.
    """
    try:
        payload = await request.json()
        logger.info(f"📩 Webhook Pix recebido: {payload}")

        provedor = identificar_provedor(payload)
        logger.info(f"📡 Provedor identificado: {provedor}")

        # define lista de transações e empresa_id inicial
        empresa_id = None
        if provedor == "sicredi":
            transactions = payload.get("pix", [])
            if not transactions:
                raise HTTPException(status_code=400, detail="Payload Sicredi inválido.")
            chave_pix = transactions[0].get("chave")
            if not chave_pix:
                raise HTTPException(status_code=400, detail="Chave Pix ausente no payload.")
            empresa_data = await get_empresa_by_chave_pix(chave_pix)
            if not empresa_data or not empresa_data.get("empresa_id"):
                raise HTTPException(status_code=400, detail="Empresa não encontrada para a chave Pix.")
            empresa_id = empresa_data["empresa_id"]

        elif provedor == "asaas":
            payment = payload.get("payment")
            if not isinstance(payment, dict):
                raise HTTPException(status_code=400, detail="Payload Asaas inválido.")
            transactions = [payment]
            # empresa_id será buscado pelo txid ao processar

        elif provedor == "rede":
            # Rede envia o JSON diretamente
            transactions = [payload]
            # empresa_id será buscado pelo txid ao processar

        else:
            raise HTTPException(status_code=400, detail="Provedor de webhook não suportado.")

        # processa em background
        asyncio.create_task(process_pix_webhook(transactions, provedor, empresa_id))
        return {"status": "success", "message": f"Webhook {provedor} recebido com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook Pix: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook Pix")


async def process_pix_webhook(transactions: list, provedor: str, empresa_id: str):
    """
    Processa notificações Pix de diferentes provedores em background.
    Atualiza o status do pagamento e dispara o webhook externo configurado.
    """
    try:
        for trx in transactions:
            # extrai txid e status conforme provedor
            if provedor == "sicredi":
                txid = trx.get("txid")
                status = trx.get("status")
            elif provedor == "asaas":
                txid = trx.get("id")
                status = trx.get("status")
                if not empresa_id:
                    # recupera empresa_id pelo pagamento já salvo
                    payment = await get_payment(txid, None)
                    empresa_id = payment.get("empresa_id") if payment else None
            elif provedor == "rede":
                txid = trx.get("externalReference") or trx.get("reference")
                status = trx.get("status")
                if not empresa_id:
                    payment = await get_payment(txid, None)
                    empresa_id = payment.get("empresa_id") if payment else None
            else:
                continue  # não deve ocorrer

            if not txid or not status or not empresa_id:
                logger.warning(f"⚠️ Dados insuficientes ({provedor}): {trx}")
                continue

            # atualiza status no banco
            await update_payment_status(txid, empresa_id, status.lower())
            logger.info(f"✅ Pagamento {txid} atualizado para {status} (empresa {empresa_id}, provedor {provedor})")

            # dispara webhook externo se configurado
            payment = await get_payment(txid, empresa_id)
            if payment and payment.get("webhook_url"):
                await notify_user_webhook(payment["webhook_url"], {
                    "transaction_id": txid,
                    "status": status,
                    "provedor": provedor,
                    "payload": trx
                })

    except Exception as e:
        logger.error(f"❌ Erro no processamento do webhook ({provedor}): {e}")


def identificar_provedor(payload: dict) -> str:
    """
    Identifica o provedor de pagamento com base na estrutura do payload.
    """
    if "pix" in payload and isinstance(payload["pix"], list):
        return "sicredi"
    if "payment" in payload and isinstance(payload["payment"], dict):
        return "asaas"
    if "externalReference" in payload or "reference" in payload:
        return "rede"
    return "unknown"
