import redis
from redis import Redis
from urllib.parse import urlparse
from payment_kode_api.app.core.config import settings
from loguru import logger


def create_redis_client() -> Redis:
    """Cria cliente Redis com configuração segura e tratamento de erros robusto."""
    try:
        conn_params = {
            "decode_responses": True,  # Retorna strings em vez de bytes
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "health_check_interval": 30
        }

        if settings.REDIS_URL:
            parsed_url = urlparse(settings.REDIS_URL)

            logger.info(f"🔄 Conectando ao Redis via URL segura: {parsed_url.hostname}")

            return Redis.from_url(settings.REDIS_URL, **conn_params)

        logger.info(f"🔄 Conectando ao Redis via parâmetros individuais: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        return Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            username=settings.REDIS_USERNAME,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            ssl=settings.REDIS_USE_SSL,
            **conn_params
        )

    except redis.AuthenticationError as e:
        logger.critical(f"❌ Falha de autenticação no Redis: {str(e)}")
        raise
    except redis.ConnectionError as e:
        logger.error(f"❌ Erro de conexão com o Redis: {str(e)}")
        raise
    except redis.TimeoutError as e:
        logger.warning(f"⚠️ Timeout ao conectar ao Redis: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao conectar ao Redis: {str(e)}")
        raise


_redis_client = None


def get_redis_client() -> Redis:
    """Retorna um cliente Redis singleton para evitar reconexões desnecessárias."""
    global _redis_client
    if _redis_client is None:
        _redis_client = create_redis_client()
    return _redis_client


def test_redis_connection() -> bool:
    """Testa a conexão com Redis de forma robusta."""
    try:
        client = get_redis_client()
        return client.ping()
    except redis.AuthenticationError as e:
        logger.critical(f"❌ Autenticação falhou no Redis: {str(e)}")
    except redis.ConnectionError as e:
        logger.error(f"❌ Erro de conexão ao testar Redis: {str(e)}")
    except redis.TimeoutError as e:
        logger.warning(f"⚠️ Timeout ao testar conexão com Redis: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao testar Redis: {str(e)}")
    return False


if __name__ == "__main__":
    if test_redis_connection():
        logger.success("✅ Conexão com Redis estabelecida com sucesso!")
    else:
        logger.error("❌ Falha na conexão com Redis")

__all__ = ["get_redis_client", "test_redis_connection"]
