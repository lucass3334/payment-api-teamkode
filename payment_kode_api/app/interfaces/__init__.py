# payment_kode_api/app/interfaces/__init__.py

from typing import Protocol, Dict, Any, List, Optional, Union
from decimal import Decimal
from datetime import datetime


# ========== INTERFACES PRINCIPAIS DE REPOSITÓRIO ==========

class PaymentRepositoryInterface(Protocol):
    """Interface para operações de pagamento"""
    
    async def save_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]: ...
    
    async def get_payment(self, transaction_id: str, empresa_id: str) -> Optional[Dict[str, Any]]: ...
    
    async def update_payment_status(
        self, 
        transaction_id: str, 
        empresa_id: str, 
        status: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]: ...
    
    async def get_payment_by_txid(self, txid: str) -> Optional[Dict[str, Any]]: ...
    
    async def update_payment_status_by_txid(
        self,
        txid: str,
        empresa_id: str, 
        status: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]: ...
    
    async def get_payments_by_cliente(
        self, 
        empresa_id: str, 
        cliente_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]: ...


class CustomerRepositoryInterface(Protocol):
    """Interface para operações de cliente"""
    
    async def get_or_create_cliente(self, empresa_id: str, customer_data: Dict[str, Any]) -> str: ...
    
    async def get_cliente_by_external_id(
        self, 
        empresa_id: str, 
        external_id: str
    ) -> Optional[Dict[str, Any]]: ...
    
    async def get_cliente_by_id(self, cliente_id: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_cliente_by_cpf_cnpj(self, cpf_cnpj: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_cliente_by_email(self, email: str) -> Optional[Dict[str, Any]]: ...
    
    async def update_cliente(self, cliente_id: str, updates: Dict[str, Any]) -> bool: ...
    
    async def delete_cliente(self, cliente_id: str) -> bool: ...
    
    async def list_clientes_empresa(self, empresa_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]: ...
    
    async def search_clientes(self, empresa_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]: ...
    
    # Métodos de endereço
    async def create_or_update_endereco(self, cliente_id: str, customer_data: Dict[str, Any]) -> Optional[str]: ...
    
    async def get_enderecos_cliente(self, cliente_id: str) -> List[Dict[str, Any]]: ...
    
    async def get_endereco_principal_cliente(self, cliente_id: str) -> Optional[Dict[str, Any]]: ...
    
    # Métodos de estatísticas
    async def get_cliente_stats_summary(self, empresa_id: str) -> Dict[str, Any]: ...


class CardRepositoryInterface(Protocol):
    """Interface para operações de cartões tokenizados"""
    
    async def save_tokenized_card(self, card_data: Dict[str, Any]) -> Dict[str, Any]: ...
    
    async def get_tokenized_card(self, card_token: str) -> Optional[Dict[str, Any]]: ...
    
    async def delete_tokenized_card(self, card_token: str) -> bool: ...
    
    async def get_cards_by_cliente(self, empresa_id: str, cliente_id: str) -> List[Dict[str, Any]]: ...


class ConfigRepositoryInterface(Protocol):
    """Interface para configurações de empresa"""
    
    async def get_empresa_config(self, empresa_id: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_sicredi_token_or_refresh(self, empresa_id: str) -> str: ...
    
    async def get_empresa_gateways(self, empresa_id: str) -> Optional[Dict[str, str]]: ...
    
    async def atualizar_config_gateway(self, payload: Dict[str, Any]) -> bool: ...


class AsaasCustomerInterface(Protocol):
    """Interface para gestão de clientes Asaas"""
    
    async def get_asaas_customer(self, empresa_id: str, local_customer_id: str) -> Optional[str]: ...
    
    async def save_asaas_customer(self, empresa_id: str, local_customer_id: str, asaas_customer_id: str) -> None: ...
    
    async def get_or_create_asaas_customer(self, empresa_id: str, local_customer_id: str, customer_data: Dict[str, Any]) -> str: ...


# ========== INTERFACES DE SERVIÇOS ==========

class CustomerServiceInterface(Protocol):
    """Interface para serviços de cliente"""
    
    def extract_customer_data_from_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]: ...
    
    def extract_cpf_cnpj(self, customer_data: Dict[str, Any]) -> Optional[str]: ...
    
    def extract_nome(self, customer_data: Dict[str, Any]) -> Optional[str]: ...
    
    def extract_telefone(self, customer_data: Dict[str, Any]) -> Optional[str]: ...
    
    def has_address_data(self, customer_data: Dict[str, Any]) -> bool: ...
    
    def extract_address_data(self, customer_data: Dict[str, Any]) -> Dict[str, str]: ...
    
    def generate_external_id(self, cpf_cnpj: Optional[str], email: Optional[str]) -> str: ...


class PaymentValidatorInterface(Protocol):
    """Interface para validações de pagamento"""
    
    def validate_installments_by_gateway(
        self, 
        installments: int, 
        gateway: str, 
        amount: Decimal
    ) -> int: ...
    
    def validate_payment_amount(self, amount: Union[Decimal, float, str]) -> Decimal: ...
    
    def validate_transaction_id(self, transaction_id: str) -> str: ...
    
    def validate_txid(self, txid: str) -> str: ...
    
    def validate_cpf_cnpj(self, document: str) -> str: ...
    
    def validate_phone(self, phone: str) -> str: ...
    
    def validate_email(self, email: str) -> str: ...
    
    def validate_card_number(self, card_number: str) -> str: ...
    
    def validate_expiration_date(self, month: str, year: str) -> tuple[str, str]: ...
    
    def validate_security_code(self, cvv: str) -> str: ...
    
    def validate_pix_key(self, pix_key: str) -> str: ...


class WebhookServiceInterface(Protocol):
    """Interface para serviços de webhook"""
    
    async def notify_user_webhook(self, webhook_url: str, data: Dict[str, Any]) -> None: ...
    
    async def process_webhook(self, provider: str, payload: Dict[str, Any]) -> bool: ...


class CertificateServiceInterface(Protocol):
    """Interface para gestão de certificados"""
    
    async def load_certificates_from_bucket(self, empresa_id: str) -> Dict[str, bytes]: ...
    
    async def validate_certificates(self, empresa_id: str) -> bool: ...
    
    async def upload_cert_file(self, empresa_id: str, filename: str, file_bytes: bytes) -> bool: ...
    
    async def download_cert_file(self, empresa_id: str, filename: str) -> Optional[bytes]: ...


class TokenServiceInterface(Protocol):
    """Interface para gestão de tokens"""
    
    async def get_sicredi_token_or_refresh(self, empresa_id: str) -> str: ...
    
    async def validate_access_token(self, token: str) -> Optional[Dict[str, Any]]: ...


# ========== INTERFACES DE GATEWAY ==========

class PaymentGatewayInterface(Protocol):
    """Interface base para gateways de pagamento"""
    
    async def process_payment(self, **kwargs) -> Dict[str, Any]: ...
    
    async def get_payment_status(self, transaction_id: str) -> Dict[str, Any]: ...
    
    async def create_refund(self, transaction_id: str, amount: Optional[float] = None) -> Dict[str, Any]: ...


class SicrediGatewayInterface(Protocol):
    """Interface específica do Sicredi"""
    
    async def create_pix_payment(self, empresa_id: str, **kwargs) -> Dict[str, Any]: ...
    
    async def create_pix_refund(self, empresa_id: str, txid: str, amount: Optional[float] = None) -> Dict[str, Any]: ...
    
    async def get_access_token(self, empresa_id: str) -> str: ...
    
    async def register_webhook(self, empresa_id: str, chave_pix: str) -> Any: ...


class RedeGatewayInterface(Protocol):
    """Interface específica da Rede"""
    
    async def create_payment(self, empresa_id: str, **kwargs) -> Dict[str, Any]: ...
    
    async def create_refund(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]: ...
    
    async def tokenize_card(self, empresa_id: str, card_data: Dict[str, Any]) -> str: ...
    
    async def capture_transaction(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]: ...
    
    async def get_transaction(self, empresa_id: str, transaction_id: str) -> Dict[str, Any]: ...


class AsaasGatewayInterface(Protocol):
    """Interface específica do Asaas"""
    
    async def create_payment(
        self, 
        empresa_id: str, 
        amount: float, 
        payment_type: str, 
        transaction_id: str,
        customer_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]: ...
    
    async def create_refund(self, empresa_id: str, transaction_id: str) -> Dict[str, Any]: ...
    
    async def tokenize_card(self, empresa_id: str, card_data: Dict[str, Any]) -> str: ...
    
    async def get_payment_status(self, empresa_id: str, transaction_id: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_pix_qr_code(self, empresa_id: str, payment_id: str) -> Dict[str, Any]: ...
    
    async def list_pix_keys(self, empresa_id: str) -> List[Dict[str, Any]]: ...
    
    async def validate_pix_key(self, empresa_id: str, chave_pix: str) -> None: ...


# ========== INTERFACES DE STORAGE E CACHE ==========

class FileStorageInterface(Protocol):
    """Interface para storage de arquivos (Supabase Storage)"""
    
    async def upload_file(self, path: str, content: bytes) -> bool: ...
    
    async def download_file(self, path: str) -> Optional[bytes]: ...
    
    async def delete_file(self, path: str) -> bool: ...
    
    async def ensure_folder_exists(self, empresa_id: str, bucket: str) -> bool: ...


class CacheRepositoryInterface(Protocol):
    """Interface para operações de cache (Redis)"""
    
    async def get(self, key: str) -> Optional[str]: ...
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool: ...
    
    async def delete(self, key: str) -> bool: ...
    
    async def exists(self, key: str) -> bool: ...


# ========== INTERFACES DE EMPRESA ==========

class EmpresaRepositoryInterface(Protocol):
    """Interface para operações de empresa"""
    
    async def save_empresa(self, data: Dict[str, Any]) -> Dict[str, Any]: ...
    
    async def get_empresa(self, cnpj: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_empresa_by_token(self, access_token: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_empresa_by_chave_pix(self, chave_pix: str) -> Optional[Dict[str, Any]]: ...
    
    async def save_empresa_certificados(
        self, 
        empresa_id: str, 
        sicredi_cert_base64: str, 
        sicredi_key_base64: str, 
        sicredi_ca_base64: Optional[str] = None
    ) -> Dict[str, Any]: ...
    
    async def get_empresa_certificados(self, empresa_id: str) -> Optional[Dict[str, Any]]: ...


# ========== EXPORTS COMPLETOS ==========

__all__ = [
    # Repositórios principais
    "PaymentRepositoryInterface",
    "CustomerRepositoryInterface", 
    "CardRepositoryInterface",
    "ConfigRepositoryInterface",
    "AsaasCustomerInterface",
    "EmpresaRepositoryInterface",
    
    # Serviços
    "CustomerServiceInterface",
    "PaymentValidatorInterface",
    "WebhookServiceInterface",
    "CertificateServiceInterface",
    "TokenServiceInterface",
    
    # Gateways
    "PaymentGatewayInterface",
    "SicrediGatewayInterface",
    "RedeGatewayInterface", 
    "AsaasGatewayInterface",
    
    # Storage e Cache
    "FileStorageInterface",
    "CacheRepositoryInterface",
]