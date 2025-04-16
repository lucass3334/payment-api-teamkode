from fastapi import APIRouter, HTTPException, Request, Depends
import asyncio
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database import update_payment_status, get_empresa_by_chave_pix
from payment_kode_api.app.security.auth import validate_access_token  # 🔹 Para autenticação multiempresas

router = APIRouter()

@router.post("/webhook/pix")
async def pix_webhook(request: Request, empresa: dict = Depends(validate_access_token, use_cache=False)):
    """
    Webhook genérico para notificações de pagamentos via Pix.
    Suporta múltiplos players (Sicredi, Rede, Asaas).
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook Pix recebido: {payload}")

        # 🔍 Identifica o provedor pelo payload
        provedor = identificar_provedor(payload)
        logger.info(f"Provedor identificado: {provedor}")

        # 🔹 Se for Sicredi, pula autenticação e busca empresa pela chave Pix
        if provedor == "sicredi":
            chave_pix = payload.get("pix", [{}])[0].get("chave")
            if not chave_pix:
                raise HTTPException(status_code=400, detail="Chave Pix ausente no payload.")

            empresa_id = await get_empresa_by_chave_pix(chave_pix)
            if not empresa_id:
                logger.warning(f"Chave Pix recebida no webhook do Sicredi não mapeada: {chave_pix}")
                raise HTTPException(status_code=400, detail="Empresa não encontrada para a chave Pix.")
        else:
            # 🔹 Se for outro provedor, usa o `empresa_id` autenticado
            empresa_id = empresa["empresa_id"]

        # 🔹 Processamento assíncrono sem bloquear a requisição
        asyncio.create_task(process_pix_webhook(payload, provedor, empresa_id))

        return {"status": "success", "message": f"Webhook {provedor} recebido"}

    except HTTPException as e:
        logger.error(f"Erro HTTP no webhook Pix: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook Pix: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook Pix")


async def process_pix_webhook(payload: dict, provedor: str, empresa_id: str):
    """
    Processa notificações Pix de diferentes provedores em background.
    """
    try:
        for transaction in payload.get("pix", []):
            transaction_id = transaction.get("txid")
            status = transaction.get("status")

            if not transaction_id or not status:
                logger.warning(f"Transação mal formatada: {transaction}")
                continue  # Ignora transações inválidas

            update_payment_status(transaction_id, empresa_id, status)
            logger.info(f"Pagamento {transaction_id} atualizado para {status} na empresa {empresa_id} ({provedor})")

    except Exception as e:
        logger.error(f"Erro no processamento assíncrono do webhook ({provedor}): {str(e)}")


def identificar_provedor(payload: dict) -> str:
    """
    Identifica o provedor de pagamento com base no payload.
    """
    if "pix" in payload and isinstance(payload["pix"], list):
        return "sicredi"
    if "externalReference" in payload or "reference" in payload:
        return "rede"
    return "asaas"  # Padrão para fallback
