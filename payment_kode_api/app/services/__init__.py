from .gateways.asaas_client import create_asaas_payment
from .gateways.sicredi_client import create_sicredi_pix_payment
from .gateways.rede_client import create_rede_payment
from .config_service import get_empresa_credentials, create_temp_cert_files  # 🔹 Gerenciamento de credenciais e certificados
from .gateways.payment_payload_mapper import (  # 🔹 Adiciona o mapeador ao init
    map_to_sicredi_payload,
    map_to_asaas_pix_payload,
    map_to_rede_payload,
    map_to_asaas_credit_payload
)

__all__ = [
    "create_asaas_payment",
    "create_sicredi_pix_payment",
    "create_rede_payment",
    "get_empresa_credentials",  # 🔹 Agora disponível para importação
    "create_temp_cert_files",  # 🔹 Adicionado para uso de certificados
    "map_to_sicredi_payload",  # 🔹 Mapeador para Sicredi
    "map_to_asaas_pix_payload",  # 🔹 Mapeador para Asaas (Pix)
    "map_to_rede_payload",  # 🔹 Mapeador para Rede (Crédito)
    "map_to_asaas_credit_payload",  # 🔹 Mapeador para Asaas (Crédito)
]
