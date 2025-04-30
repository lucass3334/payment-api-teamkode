# payment_kode_api/app/services/__init__.py

from .gateways.asaas_client import create_asaas_payment
from .gateways.sicredi_client import create_sicredi_pix_payment
from .gateways.rede_client import create_rede_payment

from .config_service import (
    get_empresa_credentials,            # 🔹 Gerenciamento de credenciais
    load_certificates_from_bucket,      # 🔹 Carregamento direto do Supabase em memória
    build_ssl_context_from_certs,       # 🔹 Criação de SSLContext para mTLS
)

from .gateways.payment_payload_mapper import (
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload,
)

from .webhook_services import notify_user_webhook  # ✅ Novo: notificação externa ao cliente

__all__ = [
    # Pagamentos
    "create_asaas_payment",
    "create_sicredi_pix_payment",
    "create_rede_payment",

    # Configurações e SSL
    "get_empresa_credentials",
    "load_certificates_from_bucket",
    "build_ssl_context_from_certs",

    # Payload mappers
    "map_to_sicredi_payload",
    "map_to_asaas_pix_payload",
    "map_to_rede_payload",
    "map_to_asaas_credit_payload",

    # Webhook externo
    "notify_user_webhook",
]
