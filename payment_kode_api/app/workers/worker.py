from app.workers.tasks import celery_app
from app.utilities.logging_config import logger

if __name__ == "__main__":
    logger.info("Iniciando o Celery Worker...")
    # Inicia o worker do Celery
    celery_app.worker_main(argv=["worker", "--loglevel=info", "--concurrency=4"])
