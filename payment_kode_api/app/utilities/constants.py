# Prioridades de fallback dos gateways
GATEWAY_PRIORITY = ["sicredi", "rede", "asaas"]

# Status possíveis de pagamentos
PAYMENT_STATUSES = {
    "PENDING": "Pagamento pendente",
    "APPROVED": "Pagamento aprovado",
    "FAILED": "Pagamento falhou",
}

# Timeout para os gateways (em segundos)
GATEWAY_TIMEOUT = 30
