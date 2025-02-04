#!/bin/bash
set -e  # Faz o script falhar imediatamente se um comando falhar

echo "🔄 Inicializando entrypoint..."

# ✅ Verifica se as variáveis de ambiente estão carregadas
if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_KEY" ]]; then
    echo "❌ ERRO: SUPABASE_URL ou SUPABASE_KEY não foram definidas!"
    exit 1
fi

# 🔄 **Aguarda o Redis estar pronto**
echo "🔄 Aguardando Redis estar disponível..."
RETRIES=10
while [[ $RETRIES -gt 0 ]]; do
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --tls --user "$REDIS_USERNAME" --pass "$REDIS_PASSWORD" ping | grep -q "PONG"; then
        echo "✅ Redis está pronto!"
        break
    fi
    echo "⏳ Redis ainda não está pronto... Tentando novamente em 5 segundos. Tentativas restantes: $RETRIES"
    sleep 5
    ((RETRIES--))
done

if [[ $RETRIES -eq 0 ]]; then
    echo "❌ ERRO: Redis não respondeu após várias tentativas!"
    exit 1
fi

# 🔄 **Verificando conexão com Supabase**
echo "🔄 Verificando conexão com Supabase..."
SUPABASE_STATUS=0
SUPABASE_RETRIES=6
while [[ $SUPABASE_RETRIES -gt 0 ]]; do
    SUPABASE_STATUS=$(curl -s -o response.json -w "%{http_code}" "$SUPABASE_URL/rest/v1/" --header "apikey: $SUPABASE_KEY")
    
    # Verifica se recebeu um status HTTP válido e o JSON de resposta
    if [[ "$SUPABASE_STATUS" -eq 200 ]] && grep -q "swagger" response.json; then
        echo "✅ Supabase está acessível!"
        break
    fi

    echo "⏳ Supabase ainda não está pronto (Código HTTP: $SUPABASE_STATUS). Tentando novamente em 5 segundos..."
    sleep 5
    ((SUPABASE_RETRIES--))
done

if [[ $SUPABASE_RETRIES -eq 0 ]]; then
    echo "❌ ERRO: Supabase não respondeu corretamente após várias tentativas!"
    exit 1
fi

# 🔥 **Inicia o serviço corretamente**
if [[ "$1" == "worker" ]]; then
    echo "🚀 Iniciando Celery Worker..."
    exec poetry run celery -A payment_kode_api.app.workers.tasks worker --loglevel=info --concurrency=4
else
    echo "🚀 Iniciando API Web..."
    exec poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8000
fi
