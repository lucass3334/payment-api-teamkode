from celery import Celery
from app.services.asaas_client import create_asaas_payment
from app.services.sicredi_client import create_sicredi_payment
from app.services.rede_client import create_rede_payment

celery_app = Celery("tasks", broker="redis://localhost:6379/0")

@celery_app.task
def process_payment(payment_data):
    """
    Processa o pagamento com fallback entre gateways.
    """
    try:
        create_sicredi_payment(payment_data)
    except Exception:
        create_rede_payment(payment_data)
    except Exception:
        create_asaas_payment(payment_data)
