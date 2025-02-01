import os
import redis
from urllib.parse import urlparse
from payment_kode_api.app.config import settings

# Usa REDIS_URL prioritariamente
if settings.REDIS_URL:
    parsed_url = urlparse(settings.REDIS_URL)
    redis_client = redis.Redis(
        host=parsed_url.hostname,
        port=parsed_url.port,
        password=parsed_url.password,
        db=settings.REDIS_DB,
        ssl=settings.REDIS_USE_SSL  # Usa SSL se "rediss://"
    )
else:
    # Configuração manual se REDIS_URL não estiver definida
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB,
        ssl=settings.REDIS_USE_SSL  # Usa SSL se necessário
    )

# Testa conexão com Redis e captura falhas
try:
    redis_client.ping()
    print("✅ Conexão com Redis bem-sucedida!")
except redis.exceptions.AuthenticationError:
    print("❌ Erro de autenticação no Redis. Verifique sua senha.")
except redis.exceptions.ConnectionError:
    print("❌ Erro ao conectar ao Redis. Verifique a configuração.")
