import redis
import os

# Captura as variáveis de ambiente dentro do container
host = os.getenv("REDIS_HOST", "redis")
port = int(os.getenv("REDIS_PORT", 6379))
password = os.getenv("REDIS_PASSWORD", None)

print(f"Tentando conectar ao Redis em {host}:{port} com senha: {'[REDACTED]' if password else 'Sem senha'}")

try:
    r = redis.Redis(
        host=host,
        port=port,
        password=password,
        ssl=False,  # 🚨 IMPORTANTE: Ajuste se precisar de SSL!
    )
    r.ping()
    print("✅ Conectado ao Redis com sucesso!")
except Exception as e:
    print(f"❌ Erro ao conectar ao Redis: {e}")
