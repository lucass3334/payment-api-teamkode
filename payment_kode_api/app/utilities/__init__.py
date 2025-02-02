from payment_kode_api.app.utilities.logging_config import logger  

# Importação atrasada para evitar que o Celery conecte ao Redis na inicialização
def get_celery_app():
    """Retorna a instância do Celery evitando conexões prematuras."""
    from payment_kode_api.app.workers.tasks import celery_app  
    return celery_app

def get_process_payment():
    """Retorna a função de processamento de pagamento evitando conexão antecipada."""
    from payment_kode_api.app.workers.tasks import process_payment  
    return process_payment

__all__ = ["get_celery_app", "get_process_payment", "logger"]
