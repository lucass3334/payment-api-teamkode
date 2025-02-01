import redis
from urllib.parse import urlparse
from payment_kode_api.app.config import settings

# Configuração do Redis
if settings.REDIS_URL:
    parsed_url = urlparse(settings.REDIS_URL)
    redis_client = redis.Redis(
        host=parsed_url.hostname,
        port=parsed_url.port,
        password=parsed_url.password,
        db=int(parsed_url.path.lstrip("/") or settings.REDIS_DB),  # Garante que o db seja numérico
        ssl=settings.REDIS_USE_SSL or False,  # Usa SSL se necessário
        ssl_cert_reqs=None if settings.REDIS_USE_SSL else "required"  # Ignora verificação de certificado caso necessário
    )
else:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB,
        ssl=settings.REDIS_USE_SSL or False,  # Garante que não seja None
        ssl_cert_reqs=None if settings.REDIS_USE_SSL else "required"
    )

# Testa conexão com Redis e captura falhas
try:
    redis_client.ping()
    print("✅ Conexão com Redis bem-sucedida!")
except redis.exceptions.AuthenticationError:
    print("❌ Erro de autenticação no Redis. Verifique sua senha.")
except redis.exceptions.ConnectionError:
    print("❌ Erro ao conectar ao Redis. Verifique a configuração.")
except redis.exceptions.ResponseError as e:
    print(f"❌ Erro no protocolo Redis: {e}")
