#!/bin/sh

echo "🔄 Aguardando Redis estar pronto..."

# Aguarda o Redis ficar pronto antes de iniciar o Celery
while ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --tls --user "$REDIS_USERNAME" --pass "$REDIS_PASSWORD" ping | grep -q "PONG"; do
    echo "⚠️ Redis ainda não está pronto. Tentando novamente em 5s..."
    sleep 5
done

echo "✅ Redis está pronto! Iniciando Celery Worker..."
exec poetry run celery -A payment_kode_api.app.workers.tasks worker --loglevel=info
