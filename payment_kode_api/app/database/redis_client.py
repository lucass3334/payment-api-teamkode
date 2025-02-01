import os
import redis
from urllib.parse import urlparse

# Obtém a URL do Redis (prioritário para ambientes na nuvem)
REDIS_URL = os.getenv("REDIS_URL", None)

if REDIS_URL:
    # Se REDIS_URL estiver definida, faz parsing da URL
    parsed_url = urlparse(REDIS_URL)

    redis_client = redis.Redis(
        host=parsed_url.hostname,
        port=parsed_url.port,
        password=parsed_url.password,
        db=0,  # Normalmente 0, mas pode ser ajustado se necessário
        ssl=True if parsed_url.scheme == "rediss" else False  # Usa SSL se "rediss://"
    )
else:
    # Configuração manual se REDIS_URL não estiver definida
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD", None),
        db=int(os.getenv("REDIS_DB", 0)),
        ssl=True  # Mantém SSL ativado para conexões seguras na nuvem
    )

# Testa a conexão e faz log do status
try:
    redis_client.ping()
    print("✅ Conexão com Redis bem-sucedida!")
except redis.exceptions.ConnectionError:
    print("❌ Erro ao conectar ao Redis.")
