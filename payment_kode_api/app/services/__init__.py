# payment_kode_api/app/services/__init__.py

# REMOVIDOS - Causam circular import (importam dependencies):
# from .gateways.asaas_client import (create_asaas_payment, create_asaas_refund)
# from .gateways.sicredi_client import (create_sicredi_pix_payment, create_sicredi_pix_refund)
# from .gateways.rede_client import create_rede_payment

# ✅ MANTIDOS - Certificados e Config (SEGUROS):
from .config_service import (
    get_empresa_credentials,        # 🔹 Gerenciamento de credenciais
    load_certificates_from_bucket,  # 🔹 Carregamento direto do Supabase em memória
)
from payment_kode_api.app.utilities.cert_utils import (
    build_ssl_context_from_memory as build_ssl_context_from_certs,  # 🔹 MTL SContext helper
)

# ✅ MANTIDOS - Payload Mappers (SEGUROS):
from .gateways.payment_payload_mapper import (
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload,
)

# ✅ MANTIDOS - Webhook Externo (SEGURO):
from .webhook_services import notify_user_webhook

__all__ = [
    # Configurações (mantidas)
    "get_empresa_credentials",
    "load_certificates_from_bucket",
    "build_ssl_context_from_certs",

    # Payload mappers (mantidos)
    "map_to_sicredi_payload",
    "map_to_asaas_pix_payload",
    "map_to_rede_payload",
    "map_to_asaas_credit_payload",

    # Webhook externo (mantido)
    "notify_user_webhook",
]