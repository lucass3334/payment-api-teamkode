from fastapi import APIRouter, HTTPException, Request
from ..utilities.logging_config import logger
from ..database.database import update_payment_status

router = APIRouter()

@router.post("/webhook/pix")
async def pix_webhook(request: Request):
    """
    Webhook opcional para notificações de pagamentos via Pix.
    Atualiza o status do pagamento no banco de dados para a empresa correspondente.
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook Pix recebido: {payload}")

        # Valida se o payload tem a chave "pix"
        if "pix" not in payload:
            logger.warning("Payload recebido não contém informações de pagamento Pix.")
            raise HTTPException(status_code=400, detail="Payload inválido")

        # Processa cada transação recebida
        for transaction in payload["pix"]:
            transaction_id = transaction.get("txid")
            status = transaction.get("status")
            empresa_id = transaction.get("empresa_id")  # Multiempresas

            if not transaction_id or not status or not empresa_id:
                logger.warning(f"Transação mal formatada ou sem empresa_id: {transaction}")
                continue  # Pula essa transação

            # Atualiza o status do pagamento no banco de dados considerando a empresa correta
            update_payment_status(transaction_id, empresa_id, status)
            logger.info(f"Pagamento {transaction_id} atualizado para {status} na empresa {empresa_id}")

        return {"status": "success", "message": "Webhook Pix processado com sucesso"}
    
    except HTTPException as e:
        logger.error(f"Erro HTTP no webhook Pix: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook Pix: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook Pix")


@router.post("/webhook/credit-card")
async def optional_credit_card_webhook(request: Request):
    """
    Webhook opcional para notificações de pagamentos via Cartão de Crédito (Rede e Asaas).
    Útil apenas para atualizações assíncronas, como chargebacks ou status pendentes.
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook opcional de Cartão de Crédito recebido: {payload}")

        # Determina se é um Webhook da Asaas ou da Rede
        transaction_id = payload.get("externalReference") or payload.get("reference")
        status = payload.get("status")
        empresa_id = payload.get("empresa_id")  # Multiempresas

        if not transaction_id or not status or not empresa_id:
            logger.warning(f"Webhook recebido com dados incompletos: {payload}")
            raise HTTPException(status_code=400, detail="Payload inválido")

        # Atualiza o status do pagamento no banco de dados apenas se houver um webhook enviado pela API
        update_payment_status(transaction_id, empresa_id, status)
        logger.info(f"Pagamento {transaction_id} atualizado para {status} via Webhook opcional na empresa {empresa_id}")

        return {"status": "success", "message": "Webhook de Cartão de Crédito processado com sucesso"}

    except HTTPException as e:
        logger.error(f"Erro HTTP no webhook de Cartão de Crédito: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook de Cartão de Crédito: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook de Cartão de Crédito")
