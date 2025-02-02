import time
import sys
from kombu import Connection
from payment_kode_api.app.workers.tasks import celery_app
from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.config import settings  # 🔹 Garantindo que as configs do Redis são carregadas corretamente

def wait_for_redis():
    """Aguarda o Redis estar pronto antes de iniciar o Celery Worker."""
    redis_url = settings.REDIS_URL
    logger.info("🔄 Aguardando Redis estar acessível antes de iniciar Celery Worker...")

    while True:
        try:
            with Connection(redis_url).connect() as conn:
                if conn.connected:
                    logger.info("✅ Redis conectado, iniciando Celery Worker...")
                    return  # Sai do loop quando a conexão for bem-sucedida
        except Exception as e:
            logger.warning(f"⚠️ Redis ainda não disponível: {e}")
            time.sleep(5)  # Aguarda 5 segundos antes de tentar novamente

def start_celery_worker():
    """Inicia o worker do Celery com configurações otimizadas."""
    logger.info("Iniciando o Celery Worker...")

    wait_for_redis()  # ✅ Só inicia o Celery depois que o Redis estiver acessível

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
        logger.error(f"❌ Erro ao iniciar o Celery Worker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_celery_worker()
