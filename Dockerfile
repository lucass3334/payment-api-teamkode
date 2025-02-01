# Base image
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala dependências de sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala o Poetry
RUN pip install --no-cache-dir poetry

# Copia os arquivos do projeto
COPY pyproject.toml poetry.lock /app/
COPY . /app/

# Instala as dependências
RUN poetry config virtualenvs.create false && poetry install --no-root

# Expõe a porta do servidor FastAPI
EXPOSE 8000

# Comando padrão para rodar a aplicação
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
