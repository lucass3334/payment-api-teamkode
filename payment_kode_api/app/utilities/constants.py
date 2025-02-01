# 🔹 Prioridades de fallback dos gateways
GATEWAY_PRIORITY = ["sicredi", "rede", "asaas"]

# 🔹 Status possíveis de pagamentos
PAYMENT_STATUSES = {
    "PENDING": "Pagamento pendente",
    "APPROVED": "Pagamento aprovado",
    "FAILED": "Pagamento falhou",
    "EXPIRED": "Pagamento expirado",
    "REFUNDED": "Pagamento reembolsado"
}

# 🔹 Timeout para os gateways (em segundos)
GATEWAY_TIMEOUT = 30

# 🔹 Tempo de expiração do QR Code Pix (em segundos)
PIX_QR_EXPIRATION = 3600  # 1 hora

# 🔹 Tipos de pagamento suportados
PAYMENT_TYPES = ["pix", "credit_card"]

# 🔹 Configuração de tentativas de fallback
MAX_RETRY_ATTEMPTS = 3  # Número máximo de tentativas para fallback entre gateways
