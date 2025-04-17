import redis
from redis import Redis
from urllib.parse import urlparse
from typing import Optional
from payment_kode_api.app.core.config import settings
from loguru import logger

# 🔁 Singleton de conexão Redis
_redis_client: Optional[Redis] = None

def create_redis_client() -> Redis:
    """
    Cria e retorna uma instância de Redis com base nas configurações do ambiente.
    Prioriza URL completa (REDIS_URL), mas pode usar os parâmetros individuais.
    """
    try:
        conn_params = {
            "decode_responses": True,
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
        logger.critical(f"❌ Autenticação falhou no Redis: {str(e)}")
        raise
    except redis.ConnectionError as e:
        logger.error(f"❌ Erro de conexão com o Redis: {str(e)}")
        raise
    except redis.TimeoutError as e:
        logger.warning(f"⚠️ Timeout ao conectar com o Redis: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao criar cliente Redis: {str(e)}")
        raise

def get_redis_client() -> Redis:
    """
    Retorna uma instância singleton do cliente Redis.
    Evita múltiplas conexões desnecessárias.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = create_redis_client()
    return _redis_client

def test_redis_connection() -> bool:
    """
    Testa a conectividade com o Redis, retornando True em caso de sucesso.
    """
    try:
        client = get_redis_client()
        return client.ping()
    except redis.AuthenticationError as e:
        logger.critical(f"❌ Autenticação falhou ao testar Redis: {str(e)}")
    except redis.ConnectionError as e:
        logger.error(f"❌ Erro de conexão ao testar Redis: {str(e)}")
    except redis.TimeoutError as e:
        logger.warning(f"⚠️ Timeout ao testar Redis: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao testar Redis: {str(e)}")
    return False

if __name__ == "__main__":
    logger.info("🧪 Testando conexão com Redis...")
    if test_redis_connection():
        logger.success("✅ Redis conectado com sucesso!")
    else:
        logger.error("❌ Falha ao conectar com Redis")

__all__ = ["get_redis_client", "test_redis_connection"]
