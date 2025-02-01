from payment_kode_api.app.workers.tasks import celery_app
from payment_kode_api.app.utilities.logging_config import logger
import sys

if __name__ == "__main__":
    logger.info("Iniciando o Celery Worker...")
    try:
        # Inicia o worker do Celery com configurações otimizadas
        celery_app.worker_main(argv=[
            "worker", 
            "--loglevel=info", 
            "--concurrency=4", 
            "--pool=eventlet"  # Usa eventlet para melhor performance assíncrona
        ])
    except Exception as e:
        logger.error(f"Erro ao iniciar o Celery Worker: {e}")
        sys.exit(1)
