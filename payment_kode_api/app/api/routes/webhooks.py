from fastapi import APIRouter, HTTPException, Request, Depends

from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database.database import update_payment_status
from payment_kode_api.app.security.auth import validate_access_token  # 🔹 Importa validação de token

router = APIRouter()

router = APIRouter()

@router.post("/webhook/pix")
async def pix_webhook(request: Request, empresa: dict = Depends(validate_access_token)):
    """
    Webhook opcional para notificações de pagamentos via Pix.
    Atualiza o status do pagamento no banco de dados para a empresa correspondente.
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook Pix recebido: {payload}")

        if "pix" not in payload:
            logger.warning("Payload recebido não contém informações de pagamento Pix.")
            raise HTTPException(status_code=400, detail="Payload inválido")

        empresa_id = empresa["empresa_id"]  # 🔹 Obtém empresa autenticada

        for transaction in payload["pix"]:
            transaction_id = transaction.get("txid")
            status = transaction.get("status")
            transaction_empresa_id = transaction.get("empresa_id")

            if not transaction_id or not status or not transaction_empresa_id:
                logger.warning(f"Transação mal formatada ou sem empresa_id: {transaction}")
                continue  # Ignora transações mal formatadas

            if transaction_empresa_id != empresa_id:
                logger.warning(f"Empresa {empresa_id} tentou atualizar um pagamento de outra empresa {transaction_empresa_id}.")
                raise HTTPException(status_code=403, detail="Acesso não autorizado para esta transação.")

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
async def optional_credit_card_webhook(request: Request, empresa: dict = Depends(validate_access_token)):
    """
    Webhook opcional para notificações de pagamentos via Cartão de Crédito (Rede e Asaas).
    Útil apenas para atualizações assíncronas, como chargebacks ou status pendentes.
    """
    try:
        payload = await request.json()
        logger.info(f"Webhook opcional de Cartão de Crédito recebido: {payload}")

        transaction_id = payload.get("externalReference") or payload.get("reference")
        status = payload.get("status")
        transaction_empresa_id = payload.get("empresa_id")

        empresa_id = empresa["empresa_id"]  # 🔹 Obtém empresa autenticada

        if not transaction_id or not status or not transaction_empresa_id:
            logger.warning(f"Webhook recebido com dados incompletos: {payload}")
            raise HTTPException(status_code=400, detail="Payload inválido")

        if transaction_empresa_id != empresa_id:
            logger.warning(f"Empresa {empresa_id} tentou atualizar um pagamento de outra empresa {transaction_empresa_id}.")
            raise HTTPException(status_code=403, detail="Acesso não autorizado para esta transação.")

        update_payment_status(transaction_id, empresa_id, status)
        logger.info(f"Pagamento {transaction_id} atualizado para {status} via Webhook opcional na empresa {empresa_id}")

        return {"status": "success", "message": "Webhook de Cartão de Crédito processado com sucesso"}

    except HTTPException as e:
        logger.error(f"Erro HTTP no webhook de Cartão de Crédito: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook de Cartão de Crédito: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook de Cartão de Crédito")
