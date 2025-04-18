# Usa uma imagem leve do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Define timezone e encoding
ENV TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PATH="/root/.local/bin:$PATH" \
    REDIS_SSL_CERT_REQS="CERT_NONE" \
    PYTHONPATH="/app"

# Instala dependências de sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    openssl \
    redis-tools \
    curl \
    ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Instala o Poetry corretamente
RUN curl -sSL https://install.python-poetry.org | python3 - \
 && poetry self update \
 && poetry config virtualenvs.create false \
 && poetry --version

# Copia arquivos de dependência para instalação
COPY pyproject.toml poetry.lock /app/
COPY README.md /app/

# Instala as dependências sem instalar o projeto como root
RUN poetry install --no-interaction --no-ansi --no-root

# Copia o restante do código da aplicação
COPY . /app/

# Permissões para scripts específicos
RUN chmod -R 755 /app/payment_kode_api/app/bugs_scripts || true

# Copia o script de entrada e define como executável
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# ❌ REMOVE este volume (certificados agora são temporários e em memória)
# RUN mkdir -p /data/certificados && chmod -R 700 /data/certificados || true

# Expõe a porta 8080
EXPOSE 8080

# Define o entrypoint para iniciar o app
ENTRYPOINT ["/app/docker-entrypoint.sh"]
