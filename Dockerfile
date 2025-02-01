# Base image
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala dependências de sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Instala o Poetry
RUN pip install --no-cache-dir poetry

# Copia os arquivos do projeto
COPY pyproject.toml poetry.lock /app/
COPY . /app/

# 🔹 Removendo a cópia local dos certificados do Sicredi
# Agora os certificados são carregados dinamicamente do banco

# Instala as dependências
RUN poetry config virtualenvs.create false && poetry install --no-root

# 🔹 Define variável de ambiente opcional para testes locais (pode ser sobrescrita no deploy)
ENV EMPRESA_ID="your_empresa_id"

# Expõe a porta do servidor FastAPI
EXPOSE 8000

# Comando padrão para rodar a aplicação
CMD ["poetry", "run", "uvicorn", "payment_kode_api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
