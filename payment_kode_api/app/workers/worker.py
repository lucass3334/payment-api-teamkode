from payment_kode_api.app.workers.tasks import celery_app
from payment_kode_api.app.utilities.logging_config import logger
import sys

def start_celery_worker():
    """Inicia o worker do Celery com configurações otimizadas."""
    logger.info("Iniciando o Celery Worker...")

    try:
        celery_app.worker_main([
            "worker", 
            "--loglevel=info", 
            "--concurrency=4",  # Ajusta número de processos
            "--pool=eventlet"   # Usa eventlet para melhorar performance assíncrona
        ])
    except KeyboardInterrupt:
        logger.warning("Celery Worker interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erro ao iniciar o Celery Worker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_celery_worker()
