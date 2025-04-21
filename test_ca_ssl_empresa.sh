#test_ca_ssl_empresa.sh
# Testa a verificação SSL com o CA da empresa
# Este script verifica se o certificado CA fornecido é confiável para o host e porta especificados.
# O script utiliza o OpenSSL para realizar a verificação e salva a saída em um arquivo de log.

#!/bin/bash

# Empresa alvo
EMPRESA_ID="3dd974c8-db75-42d6-971c-a912340bc1f8"

# Caminho para o certificado CA dessa empresa
CA_FILE="./certs/empresas/${EMPRESA_ID}/sicredi-ca.pem"

# Endpoint oficial da Sicredi (produção)
SICREDI_HOST="api-pix.sicredi.com.br"
SICREDI_PORT=443

# Verifica se o CA existe
if [[ ! -f "$CA_FILE" ]]; then
  echo "❌ Arquivo CA não encontrado: $CA_FILE"
  exit 1
fi

echo "🔍 Testando verificação SSL com CA da empresa ${EMPRESA_ID}..."
echo "   - Host: ${SICREDI_HOST}:${SICREDI_PORT}"
echo "   - CA: $CA_FILE"

echo | openssl s_client -connect "${SICREDI_HOST}:${SICREDI_PORT}" -CAfile "$CA_FILE" -verify_return_error > ca_ssl_output.log 2>&1

if grep -q "Verify return code: 0 (ok)" ca_ssl_output.log; then
  echo "✅ Verificação SSL OK: a CA fornecida é confiável."
else
  echo "❌ Verificação SSL FALHOU com essa cadeia."
  echo "📝 Veja detalhes em: ca_ssl_output.log"
fi
