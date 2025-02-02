from payment_kode_api.app.utilities.logging_config import logger  
from .tasks import process_payment, celery_app  # Importação direta para manter compatibilidade

__all__ = ["celery_app", "process_payment", "logger"]

def get_celery_app():
    """Importação atrasada do Celery para evitar conexões prematuras."""
    from .tasks import celery_app  # Importa apenas quando necessário
    return celery_app

def get_process_payment():
    """Importação atrasada da task para evitar problemas na inicialização."""
    from .tasks import process_payment  # Evita conexão precoce
    return process_payment
