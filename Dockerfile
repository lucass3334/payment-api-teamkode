# Usa uma imagem leve do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Define timezone e encoding
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV PATH="/root/.local/bin:$PATH"
ENV REDIS_SSL_CERT_REQS="CERT_NONE"

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
    && /root/.local/bin/poetry self update \
    && /root/.local/bin/poetry --version  

# Configura Poetry para não criar ambientes virtuais
RUN poetry config virtualenvs.create false

# Copia arquivos de dependência
COPY pyproject.toml poetry.lock /app/
COPY README.md /app/

# Instala dependências do projeto
RUN poetry install --no-interaction --no-ansi --no-root  

# Copia TODO o código depois de instalar dependências
COPY . /app/

# 🔒 Cria pasta no volume persistente (Render garante o /data)
RUN mkdir -p /data/certificados && chmod -R 700 /data/certificados

# Permissões em scripts internos
RUN chmod -R 755 /app/payment_kode_api/app/bugs_scripts

# Define PYTHONPATH
ENV PYTHONPATH="/app"

# Remove cache desnecessário do pip
RUN rm -rf /root/.cache/pip

# Copia script de entrada e torna executável
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Expõe porta para o Render
EXPOSE 8080

# Usa entrypoint para iniciar o app
ENTRYPOINT ["/app/docker-entrypoint.sh"]
