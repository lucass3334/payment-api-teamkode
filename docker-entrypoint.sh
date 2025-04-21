#!/bin/bash
set -euo pipefail

# 🔧 Função de log colorido com timestamp
log() {
    local GREEN="\033[0;32m"
    local YELLOW="\033[0;33m"
    local RED="\033[0;31m"
    local NC="\033[0m"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    case $1 in
        info) echo -e "${GREEN}[INFO] ${TIMESTAMP}${NC} - $2" ;;
        warn) echo -e "${YELLOW}[WARN] ${TIMESTAMP}${NC} - $2" ;;
        error) echo -e "${RED}[ERROR] ${TIMESTAMP}${NC} - $2" ;;
    esac
}

log info "🔄 Inicializando entrypoint..."

# 🔒 Garante permissões
chmod -R 755 /app/payment_kode_api/app/bugs_scripts || true

# 🔒 Verifica variáveis críticas
if [[ -z "${SUPABASE_URL}" || -z "${SUPABASE_KEY}" ]]; then
    log error "SUPABASE_URL ou SUPABASE_KEY não foram definidas!"
    exit 1
fi

# 🔄 Aguarda Supabase
log info "🔄 Verificando conexão com Supabase..."
SUPABASE_RETRIES=6
while [[ $SUPABASE_RETRIES -gt 0 ]]; do
    SUPABASE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SUPABASE_URL/rest/v1/" --header "apikey: $SUPABASE_KEY")

    if [[ "$SUPABASE_STATUS" == "200" ]]; then
        log info "✅ Supabase está acessível! (HTTP $SUPABASE_STATUS)"
        break
    fi

    log warn "⏳ Supabase não respondeu corretamente (HTTP $SUPABASE_STATUS). Tentando novamente..."
    sleep 5
    ((SUPABASE_RETRIES--))
done

if [[ $SUPABASE_RETRIES -eq 0 ]]; then
    log error "❌ Supabase não respondeu corretamente após várias tentativas!"
    exit 1
fi

# 🧼 Encerramento suave
trap 'log info "⛔ Encerrando aplicação..."; exit 0' SIGTERM SIGINT

# 🚀 Inicializa API ou Celery Worker
if [[ "${1:-}" == "worker" ]]; then
    log info "🚀 Iniciando Celery Worker..."
    exec poetry run celery -A payment_kode_api.app.workers.tasks worker --loglevel=info --concurrency=4
else
    if [[ "${API_LOCAL:-false}" == "true" ]]; then
        log info "🌐 API_LOCAL=true → Rodando localmente na porta 8080"
        exec poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8080
    else
        log info "🌐 API_LOCAL=false → Rodando em ambiente de produção (Render ou similar)"
        exec poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8080
    fi
fi
