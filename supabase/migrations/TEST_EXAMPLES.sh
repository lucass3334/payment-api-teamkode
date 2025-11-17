#!/bin/bash

# 🧪 Exemplos de Teste - Sistema PIX Multi-Gateway
# Execute esses testes após aprovar e fazer deploy da migration

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       🧪 TESTES - Sistema PIX Multi-Gateway                 ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuração
DEV_URL="https://payment-api-teamkode-1.onrender.com"
PROD_URL="https://payment-api-teamkode-7p6q.onrender.com"
TOKEN="rVTn3Ed_8_THBMp9eQQeSup76UB2ODPSR9YGDSXvuA8"

echo -e "${YELLOW}📌 Usando DEV environment: $DEV_URL${NC}"
echo ""

# ============================================================================
# TESTE 1: Backward Compatibility - Cliente envia chave_pix
# ============================================================================
echo -e "${GREEN}═══ TESTE 1: Backward Compatibility (Cliente envia chave) ═══${NC}"
echo ""
echo "curl -X POST \"$DEV_URL/payments/payment/pix\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -H \"Authorization: Bearer $TOKEN\" \\"
echo "  -d '{"
echo "    \"amount\": 10.50,"
echo "    \"chave_pix\": \"b8722c7a-0e43-43ff-b059-bf33edf4a63f\""
echo "  }'"
echo ""
echo -e "${YELLOW}Resultado esperado:${NC}"
echo "  ✅ HTTP 200"
echo "  ✅ PIX criado com sucesso"
echo "  ✅ Log: 'origem: payload'"
echo ""
echo "Executar? (pressione Enter para executar, Ctrl+C para pular)"
read -r

curl -X POST "$DEV_URL/payments/payment/pix" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "amount": 10.50,
    "chave_pix": "b8722c7a-0e43-43ff-b059-bf33edf4a63f"
  }' | jq

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# TESTE 2: Nova Funcionalidade - Cliente NÃO envia chave_pix
# ============================================================================
echo -e "${GREEN}═══ TESTE 2: Nova Funcionalidade (Busca do banco) ═══${NC}"
echo ""
echo "curl -X POST \"$DEV_URL/payments/payment/pix\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -H \"Authorization: Bearer $TOKEN\" \\"
echo "  -d '{"
echo "    \"amount\": 15.75"
echo "  }'"
echo ""
echo -e "${YELLOW}Resultado esperado:${NC}"
echo "  ✅ HTTP 200"
echo "  ✅ PIX criado usando chave do banco"
echo "  ✅ Log: 'origem: banco'"
echo ""
echo "Executar? (pressione Enter para executar, Ctrl+C para pular)"
read -r

curl -X POST "$DEV_URL/payments/payment/pix" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "amount": 15.75
  }' | jq

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# TESTE 3: Verificar Logs no Render
# ============================================================================
echo -e "${GREEN}═══ TESTE 3: Verificar Logs ═══${NC}"
echo ""
echo -e "${YELLOW}Comandos úteis para verificar logs:${NC}"
echo ""
echo "# Via MCP Render (dentro do Claude Code):"
echo "  mcp__render__list_logs(resource='srv-d0nhm41r0fns7392a46g', limit=50)"
echo ""
echo "# Buscar por 'origem: banco':"
echo "  mcp__render__list_logs(text=['origem: banco'], limit=20)"
echo ""
echo "# Buscar por 'Usando chave PIX':"
echo "  mcp__render__list_logs(text=['Usando chave PIX'], limit=20)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# TESTE 4: Verificar Dados no Banco
# ============================================================================
echo -e "${GREEN}═══ TESTE 4: Verificar Dados no Banco ═══${NC}"
echo ""
echo -e "${YELLOW}Comandos SQL úteis (via MCP Supabase):${NC}"
echo ""
echo "-- Ver todas as chaves configuradas:"
echo "SELECT empresa_id, pix_provider,"
echo "       sicredi_chave_pix IS NOT NULL as tem_sicredi,"
echo "       asaas_chave_pix IS NOT NULL as tem_asaas,"
echo "       chave_pix"
echo "FROM empresas_config;"
echo ""
echo "-- Ver apenas empresas com chaves específicas:"
echo "SELECT empresa_id, pix_provider,"
echo "       LEFT(sicredi_chave_pix, 10) as sicredi_key,"
echo "       LEFT(asaas_chave_pix, 10) as asaas_key"
echo "FROM empresas_config"
echo "WHERE sicredi_chave_pix IS NOT NULL"
echo "   OR asaas_chave_pix IS NOT NULL;"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# Resumo
# ============================================================================
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     ✅ TESTES FINALIZADOS                    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Validações necessárias:${NC}"
echo "  ✅ Teste 1 passou? (backward compatibility)"
echo "  ✅ Teste 2 passou? (busca do banco)"
echo "  ✅ Logs mostram 'origem: banco'?"
echo "  ✅ Logs mostram 'origem: payload'?"
echo "  ✅ Banco tem as novas colunas?"
echo ""
echo -e "${YELLOW}Se todos os testes passaram → aprovar para produção${NC}"
echo ""
