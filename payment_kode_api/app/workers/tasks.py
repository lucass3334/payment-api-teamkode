# payment_kode_api/app/workers/tasks.py

from celery import Celery
from kombu import Connection
import asyncio
import time

# ✅ NOVO: Imports das interfaces (SEM imports circulares)
from ..interfaces import (
    SicrediGatewayInterface,
    RedeGatewayInterface,
    AsaasGatewayInterface,
    ConfigRepositoryInterface,
)

# ✅ NOVO: Dependency injection
from ..dependencies import (
    get_sicredi_gateway,
    get_rede_gateway,
    get_asaas_gateway,
    get_config_repository,
)

from ..models.database_models import PaymentModel
from ..utilities.logging_config import logger
from ..core.config import settings

# 🔹 Inicializa o Celery sem `broker`
celery_app = Celery("tasks")

def configure_celery():
    """Configura o Celery somente após validar a conexão com Redis."""
    # ❌ DESATIVADO: Redis não está sendo usado atualmente
    # redis_url = settings.REDIS_URL
    logger.info("🔄 Configurando Celery sem Redis...")
    
    # Configuração básica sem Redis por enquanto
    celery_app.conf.update(
        task_always_eager=True,  # Executa tasks síncronamente para desenvolvimento
        task_eager_propagates=True,
    )
    logger.info("✅ Celery configurado para desenvolvimento (sem Redis)")

configure_celery()

@celery_app.task
def process_payment(payment_data: dict):
    """
    ✅ MIGRADO: Processa o pagamento com fallback entre gateways usando interfaces.
    Agora usa dependency injection para desacoplar dependências.
    """
    logger.info(f"🔹 Recebendo solicitação de pagamento: {payment_data}")

    try:
        payment = PaymentModel(**payment_data)
    except Exception as e:
        logger.error(f"❌ Erro ao validar PaymentModel: {e}")
        return {"status": "failed", "message": "Dados inválidos para o pagamento."}

    # ✅ USANDO INTERFACES: Dependency injection
    empresa_id = str(payment.empresa_id)
    config_repo = get_config_repository()
    
    # Obtém as credenciais da empresa usando interface
    try:
        credentials = asyncio.run(config_repo.get_empresa_config(empresa_id))
    except Exception as e:
        logger.error(f"❌ Erro ao obter config da empresa {empresa_id}: {e}")
        return {"status": "failed", "message": "Empresa não configurada."}

    if not credentials:
        logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada.")
        return {"status": "failed", "message": "Empresa não configurada."}

    try:
        response = None

        if payment.payment_type == "pix":
            logger.info(f"💰 Iniciando pagamento Pix via Sicredi para {payment.transaction_id}")
            
            # ✅ USANDO INTERFACE: Sicredi Gateway
            sicredi_gateway = get_sicredi_gateway()
            response = asyncio.run(
                sicredi_gateway.create_pix_payment(
                    empresa_id=empresa_id,
                    amount=payment.amount,
                    chave_pix=payment_data.get("chave_pix"),
                    txid=payment.transaction_id
                )
            )

        elif payment.payment_type == "credit_card":
            logger.info(f"💳 Iniciando pagamento via Rede para {payment.transaction_id}")
            
            # ✅ USANDO INTERFACE: Rede Gateway
            rede_gateway = get_rede_gateway()
            response = asyncio.run(
                rede_gateway.create_payment(
                    empresa_id=empresa_id,
                    transaction_id=payment.transaction_id,
                    amount=payment.amount,
                    card_data=payment_data.get("card_data")
                )
            )

        else:
            raise ValueError(f"⚠️ Tipo de pagamento inválido: {payment.payment_type}")

    except Exception as e:
        logger.error(f"❌ Erro no primeiro gateway: {e}, tentando fallback para Asaas")

        try:
            logger.info(f"🔄 Fallback: Tentando pagamento via Asaas para {payment.transaction_id}")
            
            # ✅ USANDO INTERFACE: Asaas Gateway
            asaas_gateway = get_asaas_gateway()
            response = asyncio.run(
                asaas_gateway.create_payment(
                    empresa_id=empresa_id,
                    amount=float(payment.amount),
                    payment_type=payment.payment_type,
                    transaction_id=payment.transaction_id,
                    customer_data=payment_data.get("customer", {}),
                    card_data=payment_data.get("card_data"),
                    installments=payment_data.get("installments", 1)
                )
            )
        except Exception as fallback_error:
            logger.error(f"❌ Erro no fallback via Asaas: {fallback_error}, pagamento falhou")
            return {"status": "failed", "message": str(fallback_error)}

    # Se chegou até aqui, significa que o pagamento foi processado com sucesso
    logger.info(f"✅ Pagamento processado com sucesso: {response}")
    return {"status": "approved", "response": response}


@celery_app.task
def process_refund(refund_data: dict):
    """
    ✅ NOVO: Processa estornos usando interfaces.
    """
    logger.info(f"🔄 Recebendo solicitação de estorno: {refund_data}")
    
    empresa_id = refund_data.get("empresa_id")
    transaction_id = refund_data.get("transaction_id")
    payment_type = refund_data.get("payment_type")
    amount = refund_data.get("amount")
    
    try:
        if payment_type == "pix":
            # ✅ USANDO INTERFACE: Sicredi Gateway
            sicredi_gateway = get_sicredi_gateway()
            response = asyncio.run(
                sicredi_gateway.create_pix_refund(
                    empresa_id=empresa_id,
                    txid=refund_data.get("txid"),
                    amount=amount
                )
            )
        elif payment_type == "credit_card":
            # ✅ USANDO INTERFACE: Rede Gateway
            rede_gateway = get_rede_gateway()
            response = asyncio.run(
                rede_gateway.create_refund(
                    empresa_id=empresa_id,
                    transaction_id=transaction_id,
                    amount=int(amount * 100) if amount else None
                )
            )
        else:
            raise ValueError(f"Tipo de pagamento inválido para estorno: {payment_type}")
        
        logger.info(f"✅ Estorno processado com sucesso: {response}")
        return {"status": "success", "response": response}
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar estorno: {e}")
        return {"status": "failed", "message": str(e)}


# ========== FUNÇÕES AUXILIARES ==========

def get_gateway_by_provider(provider: str, payment_type: str):
    """
    ✅ NOVO: Factory function para obter gateway correto usando interfaces.
    """
    if payment_type == "pix":
        if provider.lower() == "sicredi":
            return get_sicredi_gateway()
        elif provider.lower() == "asaas":
            return get_asaas_gateway()
    elif payment_type == "credit_card":
        if provider.lower() == "rede":
            return get_rede_gateway()
        elif provider.lower() == "asaas":
            return get_asaas_gateway()
    
    raise ValueError(f"Gateway não suportado: {provider} para {payment_type}")


# ========== EXPORTS ==========

__all__ = [
    "celery_app",
    "process_payment",
    "process_refund",
    "get_gateway_by_provider",
]