# Usa uma imagem leve do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Define timezone e encoding
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

# Instala dependências de sistema necessárias (PostgreSQL, OpenSSL, Build Essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    openssl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Instala o Poetry globalmente sem cache
RUN pip install --no-cache-dir poetry

# Copia apenas os arquivos necessários para instalar dependências primeiro (cache otimizado)
COPY pyproject.toml poetry.lock /app/

# Instala as dependências do projeto
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copia o restante do código, incluindo `bugs_scripts`
COPY payment_kode_api /app/payment_kode_api
COPY bugs_scripts /app/bugs_scripts  
# 🔹 Garante que a pasta de scripts existe antes de alterar permissões
RUN chmod -R 755 /app/bugs_scripts

# Remove arquivos temporários desnecessários
RUN rm -rf /root/.cache/pip

# Expõe a porta padrão do FastAPI
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["poetry", "run", "uvicorn", "payment_kode_api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
