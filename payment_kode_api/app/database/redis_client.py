import redis
from urllib.parse import urlparse
from payment_kode_api.app.config import settings
import ssl

def create_redis_client():
    """Factory para criar cliente Redis com configuração segura para Render.com"""
    try:
        use_ssl = settings.REDIS_USE_SSL
        cert_reqs = ssl.CERT_REQUIRED if settings.REDIS_SSL_CERT_REQS else ssl.CERT_NONE  # Correção aqui

        if settings.REDIS_URL:
            parsed_url = urlparse(settings.REDIS_URL)
            return redis.Redis(
                host=parsed_url.hostname,
                port=parsed_url.port,
                password=parsed_url.password,
                db=int(parsed_url.path.lstrip("/") or settings.REDIS_DB),
                ssl=use_ssl,
                ssl_cert_reqs=cert_reqs,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )

        return redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            ssl=use_ssl,
            ssl_cert_reqs=cert_reqs,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
    except Exception as e:
        print(f"❌ Erro ao configurar Redis: {str(e)}")
        return None

# Criação do cliente Redis
redis_client = create_redis_client()

# Teste de conexão robusto
def test_redis_connection():
    try:
        if redis_client and redis_client.ping():
            print("✅ Conexão com Redis: Operacional")
            return True
        print("❌ Redis não respondeu ao ping.")
        return False
    except redis.exceptions.AuthenticationError as e:
        print(f"❌ Falha de autenticação: {str(e)}")
    except redis.exceptions.ConnectionError as e:
        print(f"❌ Falha de conexão: Verifique host/porta - {str(e)}")
    except redis.exceptions.TimeoutError as e:
        print(f"❌ Timeout: O Redis não respondeu em 5s - {str(e)}")
    except Exception as e:
        print(f"❌ Erro inesperado: {str(e)}")
    return False

# Executa teste na inicialização
if redis_client:
    test_redis_connection()
