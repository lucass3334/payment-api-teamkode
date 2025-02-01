from celery import Celery
from payment_kode_api.app.services.asaas_client import create_asaas_payment
from payment_kode_api.app.services.sicredi_client import create_sicredi_pix_payment
from payment_kode_api.app.services.rede_client import create_rede_payment
from payment_kode_api.app.models.database_models import PaymentModel
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database.database import get_empresa_config
import asyncio

celery_app = Celery("tasks", broker="redis://localhost:6379/0")

@celery_app.task
def process_payment(payment_data: dict):
    """
    Processa o pagamento com fallback entre gateways e registra no banco.
    """
    payment = PaymentModel(**payment_data)

    # Obtém as credenciais da empresa
    empresa_id = payment.empresa_id
    credentials = get_empresa_config(empresa_id)
    if not credentials:
        logger.error(f"Configuração da empresa {empresa_id} não encontrada.")
        return {"status": "failed", "message": "Empresa não configurada."}

    try:
        response = None

        if payment.payment_type == "pix":
            logger.info(f"Iniciando pagamento Pix via Sicredi para {payment.transaction_id}")
            response = asyncio.run(
                create_sicredi_pix_payment(
                    empresa_id=empresa_id, 
                    amount=payment.amount, 
                    chave_pix=payment_data.get("chave_pix"),  # Corrigido para evitar erro
                    txid=payment.transaction_id
                )
            )
        
        elif payment.payment_type == "credit_card":
            logger.info(f"Iniciando pagamento via Rede para {payment.transaction_id}")
            response = asyncio.run(create_rede_payment(empresa_id, payment.transaction_id, payment.amount, payment_data.get("card_data")))

        else:
            raise ValueError(f"Tipo de pagamento inválido: {payment.payment_type}")

    except Exception as e:
        logger.error(f"Erro no primeiro gateway: {e}, tentando fallback para Asaas")

        try:
            logger.info(f"Fallback: Tentando pagamento via Asaas para {payment.transaction_id}")
            response = asyncio.run(
                create_asaas_payment(
                    empresa_id=empresa_id,
                    amount=payment.amount,
                    payment_type=payment.payment_type,
                    transaction_id=payment.transaction_id,
                    customer=payment_data.get("customer"),
                    card_data=payment_data.get("card_data"),
                    installments=payment_data.get("installments", 1)
                )
            )
        except Exception as fallback_error:
            logger.error(f"Erro no fallback via Asaas: {fallback_error}, pagamento falhou")
            payment.status = "failed"
            return {"status": "failed", "message": str(fallback_error)}

    # Se chegou até aqui, significa que o pagamento foi processado com sucesso
    payment.status = "approved"
    logger.info(f"Pagamento processado com sucesso: {response}")
    return {"status": "approved", "response": response}
