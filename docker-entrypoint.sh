#!/bin/bash
set -e  # Faz o script falhar imediatamente se um comando falhar

# Função de log com timestamps e cores
log() {
    local GREEN="\033[0;32m"
    local YELLOW="\033[0;33m"
    local RED="\033[0;31m"
    local NC="\033[0m"  # No Color
    local TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    case $1 in
        info) echo -e "${GREEN}[INFO] ${TIMESTAMP}${NC} - $2" ;;
        warn) echo -e "${YELLOW}[WARN] ${TIMESTAMP}${NC} - $2" ;;
        error) echo -e "${RED}[ERROR] ${TIMESTAMP}${NC} - $2" ;;
    esac
}

log info "🔄 Inicializando entrypoint..."

# ✅ Garante que os arquivos críticos tenham permissões corretas
chmod +x /app/docker-entrypoint.sh
chmod -R 755 /app/payment_kode_api/app/bugs_scripts

# ✅ Verifica se as variáveis de ambiente estão carregadas
if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_KEY" ]]; then
    log error "SUPABASE_URL ou SUPABASE_KEY não foram definidas!"
    exit 1
fi

# 🔄 **Aguarda o Redis estar pronto**
log info "🔄 Aguardando Redis estar disponível..."
RETRIES=10
while [[ $RETRIES -gt 0 ]]; do
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --tls --user "$REDIS_USERNAME" --pass "$REDIS_PASSWORD" ping | grep -q "PONG"; then
        log info "✅ Redis está pronto!"
        break
    fi
    log warn "⏳ Redis ainda não está pronto... Tentando novamente em 5 segundos. Tentativas restantes: $RETRIES"
    sleep 5
    ((RETRIES--))
done

if [[ $RETRIES -eq 0 ]]; then
    log error "Redis não respondeu após várias tentativas!"
    exit 1
fi

# 🔄 **Verificando conexão com Supabase**
log info "🔄 Verificando conexão com Supabase..."
SUPABASE_RETRIES=6
while [[ $SUPABASE_RETRIES -gt 0 ]]; do
    SUPABASE_STATUS=$(curl -s -o response.json -w "%{http_code}" "$SUPABASE_URL/rest/v1/" --header "apikey: $SUPABASE_KEY")
    
    if [[ "$SUPABASE_STATUS" -eq 200 ]] && [[ -s response.json ]] && grep -q "swagger" response.json; then
        log info "✅ Supabase está acessível!"
        break
    fi

    log warn "⏳ Supabase ainda não está pronto (Código HTTP: $SUPABASE_STATUS). Tentando novamente em 5 segundos..."
    sleep 5
    ((SUPABASE_RETRIES--))
done

if [[ $SUPABASE_RETRIES -eq 0 ]]; then
    log error "Supabase não respondeu corretamente após várias tentativas!"
    exit 1
fi

# 🔥 **Tratamento de sinais para encerramento seguro**
trap 'log info "⛔ Encerrando aplicação..."; exit 0' SIGTERM SIGINT

# 🔥 **Inicia o serviço corretamente**
if [[ "$1" == "worker" ]]; then
    log info "🚀 Iniciando Celery Worker..."
    exec poetry run celery -A payment_kode_api.app.workers.tasks worker --loglevel=info --concurrency=4
else
    log info "🚀 Iniciando API Web..."
    exec poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8000 --workers 4
fi
