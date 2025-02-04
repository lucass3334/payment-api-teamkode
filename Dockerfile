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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Instala o Poetry corretamente e garante que está atualizado
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && /root/.local/bin/poetry self update \
    && /root/.local/bin/poetry --version  

# Configura Poetry para não criar ambientes virtuais
RUN poetry config virtualenvs.create false

# Copia apenas os arquivos de dependências para otimizar cache
COPY pyproject.toml poetry.lock /app/

# ✅ Copia o README.md para evitar erro no Poetry
COPY README.md /app/

# Instala dependências do projeto via Poetry (sem instalar o próprio projeto)
RUN poetry install --no-interaction --no-ansi --no-root  

# Copia TODO o código corretamente (agora depois da instalação das dependências)
COPY . /app/

# Ajusta permissões do diretório de scripts
RUN chmod -R 755 /app/payment_kode_api/app/bugs_scripts

# Adiciona o diretório `/app` ao PYTHONPATH
ENV PYTHONPATH="/app"

# Remove arquivos temporários
RUN rm -rf /root/.cache/pip

# 🔹 Copia o script de entrypoint e torna executável
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Expõe a porta do FastAPI
EXPOSE 8000

# Define o entrypoint correto
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Comando para iniciar a aplicação
CMD ["poetry", "run", "uvicorn", "payment_kode_api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
