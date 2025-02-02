# Usa uma imagem leve do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Define timezone e encoding
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

# Instala dependências de sistema necessárias (PostgreSQL, OpenSSL, Build Essentials, Redis CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    openssl \
    redis-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configura variável de ambiente para permitir o uso do Redis via SSL
ENV REDIS_SSL_CERT_REQS=CERT_NONE

# Instala o Poetry globalmente sem cache
RUN pip install --no-cache-dir poetry

# Copia apenas os arquivos necessários para instalar dependências primeiro (cache otimizado)
COPY pyproject.toml poetry.lock /app/

# Garante que as dependências sejam instaladas mesmo que `poetry.lock` não exista
RUN poetry config virtualenvs.create false \
    && [ -f poetry.lock ] && poetry install --no-root --no-interaction --no-ansi || poetry install --no-interaction --no-ansi

# Copia TODO o código da API corretamente
COPY payment_kode_api /app/payment_kode_api

# Garante que a pasta de scripts de debug tenha as permissões corretas
RUN mkdir -p /app/payment_kode_api/app/bugs_scripts && chmod -R 755 /app/payment_kode_api/app/bugs_scripts

# Adiciona o diretório `/app` ao PYTHONPATH para garantir que os módulos sejam encontrados
ENV PYTHONPATH="/app"

# Remove arquivos temporários desnecessários
RUN rm -rf /root/.cache/pip

# 🔹 Copia o script de entrypoint e torna executável
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Expõe a porta padrão do FastAPI
EXPOSE 8000

# Define o entrypoint padrão
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Comando para iniciar a aplicação
CMD ["poetry", "run", "uvicorn", "payment_kode_api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
