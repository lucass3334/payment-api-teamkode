import redis
from redis import Redis
from urllib.parse import urlparse
from payment_kode_api.app.core.config import settings
from loguru import logger
import ssl

def create_redis_client() -> Redis:
    """Cria cliente Redis com configuração segura e tratamento de erros robusto."""
    try:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = settings.REDIS_SSL_CERT_REQS

        conn_params = {
            "ssl": settings.REDIS_USE_SSL,
            "ssl_cert_reqs": ssl_context.verify_mode,
            "ssl_ca_certs": None,
            "decode_responses": True,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "health_check_interval": 30
        }

        if settings.REDIS_URL:
            logger.debug(f"Conectando via URL: {settings.REDIS_URL.split('@')[-1]}")
            return Redis.from_url(settings.REDIS_URL, **conn_params)

        logger.debug("Conectando via parâmetros individuais")
        return Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            username=settings.REDIS_USERNAME,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            **conn_params
        )

    except redis.AuthenticationError as e:
        logger.critical(f"Falha de autenticação: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Erro na conexão com Redis: {str(e)}")
        raise

_redis_client = None

def get_redis_client() -> Redis:
    """Getter singleton para o cliente Redis com reconexão automática."""
    global _redis_client
    if not _redis_client or not _redis_client.ping():
        _redis_client = create_redis_client()
    return _redis_client

def test_redis_connection() -> bool:  # ✅ Versão corrigida
    """Testa a conexão com Redis de forma robusta."""
    try:
        client = get_redis_client()
        return bool(client.ping())
    except redis.exceptions.AuthenticationError as e:
        logger.critical(f"Autenticação falhou: {str(e)}")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Conexão falhou: {str(e)}")
    except redis.exceptions.TimeoutError as e:
        logger.warning(f"Timeout: {str(e)}")
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}")
    return False

if __name__ == "__main__":
    if test_redis_connection():
        logger.success("✅ Conexão com Redis estabelecida com sucesso!")
    else:
        logger.error("❌ Falha na conexão com Redis")

__all__ = ["get_redis_client", "test_redis_connection"]  # ✅ Exportações explícitas