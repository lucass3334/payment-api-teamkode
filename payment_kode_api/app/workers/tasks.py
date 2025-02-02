from celery import Celery
from kombu import Connection
from payment_kode_api.app.services.asaas_client import create_asaas_payment
from payment_kode_api.app.services.sicredi_client import create_sicredi_pix_payment
from payment_kode_api.app.services.rede_client import create_rede_payment
from payment_kode_api.app.models.database_models import PaymentModel
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database.database import get_empresa_config
from payment_kode_api.app.config import settings  # ✅ Configuração segura
import asyncio
import time

# 🔹 Inicializa o Celery sem `broker`
celery_app = Celery("tasks")

def configure_celery():
    """Configura o Celery somente após validar a conexão com Redis."""
    redis_url = settings.REDIS_URL
    logger.info("🔄 Testando conexão com Redis antes de configurar Celery...")

    while True:
        try:
            with Connection(redis_url).connect() as conn:
                if conn.connected:
                    logger.info("✅ Redis está acessível, configurando Celery...")
                    celery_app.conf.update(
                        broker_url=redis_url,
                        broker_use_ssl={
                            "ssl_cert_reqs": settings.REDIS_SSL_CERT_REQS
                        } if settings.REDIS_USE_SSL else None
                    )
                    return  # Sai do loop quando o Redis estiver pronto
        except Exception as e:
            logger.warning(f"⚠️ Redis ainda não está disponível: {e}")
            time.sleep(5)  # Aguarda 5 segundos antes de tentar novamente

configure_celery()  # ✅ Só configura Celery quando o Redis estiver pronto

@celery_app.task
def process_payment(payment_data: dict):
    """
    Processa o pagamento com fallback entre gateways e registra no banco.
    """
    logger.info(f"🔹 Recebendo solicitação de pagamento: {payment_data}")

    try:
        payment = PaymentModel(**payment_data)  # ✅ Valida os dados corretamente
    except Exception as e:
        logger.error(f"❌ Erro ao validar PaymentModel: {e}")
        return {"status": "failed", "message": "Dados inválidos para o pagamento."}

    # Obtém as credenciais da empresa de maneira síncrona
    empresa_id = payment.empresa_id
    credentials = asyncio.run(get_empresa_config(empresa_id))  # ✅ Corrigindo chamada assíncrona

    if not credentials:
        logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada.")
        return {"status": "failed", "message": "Empresa não configurada."}

    try:
        response = None

        if payment.payment_type == "pix":
            logger.info(f"💰 Iniciando pagamento Pix via Sicredi para {payment.transaction_id}")
            response = asyncio.run(
                create_sicredi_pix_payment(
                    empresa_id=empresa_id, 
                    amount=payment.amount, 
                    chave_pix=payment_data.get("chave_pix"),
                    txid=payment.transaction_id
                )
            )

        elif payment.payment_type == "credit_card":
            logger.info(f"💳 Iniciando pagamento via Rede para {payment.transaction_id}")
            response = asyncio.run(
                create_rede_payment(
                    empresa_id, 
                    payment.transaction_id, 
                    payment.amount, 
                    payment_data.get("card_data")
                )
            )

        else:
            raise ValueError(f"⚠️ Tipo de pagamento inválido: {payment.payment_type}")

    except Exception as e:
        logger.error(f"❌ Erro no primeiro gateway: {e}, tentando fallback para Asaas")

        try:
            logger.info(f"🔄 Fallback: Tentando pagamento via Asaas para {payment.transaction_id}")
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
            logger.error(f"❌ Erro no fallback via Asaas: {fallback_error}, pagamento falhou")
            payment.status = "failed"
            return {"status": "failed", "message": str(fallback_error)}

    # Se chegou até aqui, significa que o pagamento foi processado com sucesso
    payment.status = "approved"
    logger.info(f"✅ Pagamento processado com sucesso: {response}")
    return {"status": "approved", "response": response}
