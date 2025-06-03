# payment_kode_api/app/dependencies.py

from typing import Optional
from functools import lru_cache

from .interfaces import (
    PaymentRepositoryInterface,
    CustomerRepositoryInterface,
    ConfigRepositoryInterface,
    CustomerServiceInterface,
    PaymentValidatorInterface,
    CardRepositoryInterface,
    AsaasCustomerInterface,
    WebhookServiceInterface,
    CertificateServiceInterface,
    SicrediGatewayInterface,
    RedeGatewayInterface,
    AsaasGatewayInterface,
    EmpresaRepositoryInterface,
    FileStorageInterface,
    CacheRepositoryInterface,
)

# ========== IMPORTS DAS IMPLEMENTAÇÕES ==========

try:
    from .database.repositories import (
        PaymentRepository, 
        ConfigRepository,
        CardRepository,
        AsaasCustomerRepository,
    )
    _repositories_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar repositories: {e}")
    _repositories_available = False

try:
    from .database.customer_repository import CustomerRepository, CustomerService
    _customer_repository_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar customer_repository: {e}")
    _customer_repository_available = False

try:
    from .services.validators import PaymentValidator
    _validators_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar validators: {e}")
    _validators_available = False

try:
    from .services.webhook_services import notify_user_webhook
    _webhook_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar webhook_services: {e}")
    _webhook_available = False

try:
    from .services.config_service import (
        load_certificates_from_bucket,
        get_empresa_credentials,
    )
    _config_service_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar config_service: {e}")
    _config_service_available = False

try:
    from .database.database import (
        save_empresa as db_save_empresa,
        get_empresa as db_get_empresa,
        get_empresa_by_token as db_get_empresa_by_token,
        get_empresa_by_chave_pix as db_get_empresa_by_chave_pix,
        save_empresa_certificados as db_save_empresa_certificados,
        get_empresa_certificados as db_get_empresa_certificados,
    )
    _empresa_repository_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar empresa functions: {e}")
    _empresa_repository_available = False

try:
    from .database.supabase_storage import (
        upload_cert_file,
        download_cert_file,
        ensure_folder_exists,
    )
    _file_storage_available = True
except ImportError as e:
    print(f"⚠️ Erro ao importar file storage: {e}")
    _file_storage_available = False

# ========== IMPLEMENTAÇÕES DUMMY (FALLBACK) ==========

class DummyPaymentRepository:
    """Implementação dummy para quando repositories não estão disponíveis"""
    async def save_payment(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")
    async def get_payment(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")
    async def update_payment_status(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")
    async def get_payment_by_txid(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")
    async def update_payment_status_by_txid(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")
    async def get_payments_by_cliente(self, *args, **kwargs):
        raise NotImplementedError("PaymentRepository não disponível")

class DummyCustomerRepository:
    """Implementação dummy para quando customer_repository não está disponível"""
    async def get_or_create_cliente(self, *args, **kwargs):
        raise NotImplementedError("CustomerRepository não disponível")
    async def get_cliente_by_external_id(self, *args, **kwargs):
        raise NotImplementedError("CustomerRepository não disponível")
    async def get_cliente_by_id(self, *args, **kwargs):
        raise NotImplementedError("CustomerRepository não disponível")

class DummyConfigRepository:
    """Implementação dummy para quando repositories não estão disponíveis"""
    async def get_empresa_config(self, *args, **kwargs):
        raise NotImplementedError("ConfigRepository não disponível")
    async def get_sicredi_token_or_refresh(self, *args, **kwargs):
        raise NotImplementedError("ConfigRepository não disponível")

class DummyCardRepository:
    """Implementação dummy para cartões"""
    async def save_tokenized_card(self, *args, **kwargs):
        raise NotImplementedError("CardRepository não disponível")
    async def get_tokenized_card(self, *args, **kwargs):
        raise NotImplementedError("CardRepository não disponível")
    async def delete_tokenized_card(self, *args, **kwargs):
        raise NotImplementedError("CardRepository não disponível")

class DummyAsaasCustomerRepository:
    """Implementação dummy para clientes Asaas"""
    async def get_asaas_customer(self, *args, **kwargs):
        raise NotImplementedError("AsaasCustomerRepository não disponível")

class DummyCustomerService:
    """Implementação dummy para serviços de cliente"""
    def extract_customer_data_from_payment(self, *args, **kwargs):
        raise NotImplementedError("CustomerService não disponível")

class DummyPaymentValidator:
    """Implementação dummy para validações"""
    def validate_installments_by_gateway(self, installments: int, gateway: str, amount) -> int:
        # Fallback simples - sem validação específica
        return max(1, min(installments, 12))

class DummySicrediGateway:
    """Implementação dummy para Sicredi"""
    async def create_pix_payment(self, *args, **kwargs):
        raise NotImplementedError("Sicredi Gateway não disponível")
    async def create_pix_refund(self, *args, **kwargs):
        raise NotImplementedError("Sicredi Gateway não disponível")
    async def get_access_token(self, *args, **kwargs):
        raise NotImplementedError("Sicredi Gateway não disponível")
    async def register_webhook(self, *args, **kwargs):
        raise NotImplementedError("Sicredi Gateway não disponível")

class DummyRedeGateway:
    """Implementação dummy para Rede"""
    async def create_payment(self, *args, **kwargs):
        raise NotImplementedError("Rede Gateway não disponível")
    async def create_refund(self, *args, **kwargs):
        raise NotImplementedError("Rede Gateway não disponível")
    async def tokenize_card(self, *args, **kwargs):
        raise NotImplementedError("Rede Gateway não disponível")

class DummyAsaasGateway:
    """Implementação dummy para Asaas"""
    async def create_payment(self, *args, **kwargs):
        raise NotImplementedError("Asaas Gateway não disponível")
    async def create_refund(self, *args, **kwargs):
        raise NotImplementedError("Asaas Gateway não disponível")
    async def tokenize_card(self, *args, **kwargs):
        raise NotImplementedError("Asaas Gateway não disponível")

class DummyWebhookService:
    """Implementação dummy para webhooks"""
    async def notify_user_webhook(self, *args, **kwargs):
        raise NotImplementedError("Webhook Service não disponível")

class DummyCertificateService:
    """Implementação dummy para certificados"""
    async def load_certificates_from_bucket(self, *args, **kwargs):
        raise NotImplementedError("Certificate Service não disponível")
    async def validate_certificates(self, *args, **kwargs):
        raise NotImplementedError("Certificate Service não disponível")

class DummyEmpresaRepository:
    """Implementação dummy para EmpresaRepository"""
    async def save_empresa(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")
    async def get_empresa(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")
    async def get_empresa_by_token(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")
    async def get_empresa_by_chave_pix(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")
    async def save_empresa_certificados(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")
    async def get_empresa_certificados(self, *args, **kwargs):
        raise NotImplementedError("EmpresaRepository não disponível")

class DummyFileStorage:
    """Implementação dummy para FileStorage"""
    async def upload_file(self, *args, **kwargs):
        raise NotImplementedError("FileStorage não disponível")
    async def download_file(self, *args, **kwargs):
        raise NotImplementedError("FileStorage não disponível")
    async def delete_file(self, *args, **kwargs):
        raise NotImplementedError("FileStorage não disponível")
    async def ensure_folder_exists(self, *args, **kwargs):
        raise NotImplementedError("FileStorage não disponível")

class DummyCacheRepository:
    """Implementação dummy para CacheRepository"""
    async def get(self, *args, **kwargs):
        raise NotImplementedError("CacheRepository não disponível")
    async def set(self, *args, **kwargs):
        raise NotImplementedError("CacheRepository não disponível")
    async def delete(self, *args, **kwargs):
        raise NotImplementedError("CacheRepository não disponível")
    async def exists(self, *args, **kwargs):
        raise NotImplementedError("CacheRepository não disponível")

# ========== IMPLEMENTAÇÕES DAS INTERFACES ==========

class EmpresaRepository:
    """Implementação que usa suas funções existentes de empresa"""
    
    async def save_empresa(self, data):
        return await db_save_empresa(data)
    
    async def get_empresa(self, cnpj):
        return await db_get_empresa(cnpj)
    
    async def get_empresa_by_token(self, access_token):
        return await db_get_empresa_by_token(access_token)
    
    async def get_empresa_by_chave_pix(self, chave_pix):
        return await db_get_empresa_by_chave_pix(chave_pix)
    
    async def save_empresa_certificados(self, empresa_id, sicredi_cert_base64, sicredi_key_base64, sicredi_ca_base64=None):
        return await db_save_empresa_certificados(empresa_id, sicredi_cert_base64, sicredi_key_base64, sicredi_ca_base64)
    
    async def get_empresa_certificados(self, empresa_id):
        return await db_get_empresa_certificados(empresa_id)


class FileStorageRepository:
    """Implementação que usa supabase_storage"""
    
    async def upload_file(self, path, content):
        # Extrair empresa_id e filename do path
        parts = path.split('/')
        if len(parts) >= 2:
            empresa_id, filename = parts[0], parts[1]
            return await upload_cert_file(empresa_id, filename, content)
        return False
    
    async def download_file(self, path):
        # Extrair empresa_id e filename do path
        parts = path.split('/')
        if len(parts) >= 2:
            empresa_id, filename = parts[0], parts[1]
            return await download_cert_file(empresa_id, filename)
        return None
    
    async def delete_file(self, path):
        # Implementação básica - pode ser expandida
        return True
    
    async def ensure_folder_exists(self, empresa_id, bucket):
        return await ensure_folder_exists(empresa_id, bucket)


class CertificateServiceImplementation:
    """Implementação completa que usa config_service"""
    
    def __init__(self, file_storage=None):
        self.file_storage = file_storage or FileStorageRepository()
    
    async def load_certificates_from_bucket(self, empresa_id):
        # Usar import local para evitar circular
        from .services.config_service import load_certificates_from_bucket
        return await load_certificates_from_bucket(empresa_id)
    
    async def validate_certificates(self, empresa_id):
        try:
            certs = await self.load_certificates_from_bucket(empresa_id)
            required_keys = {"cert_path", "key_path"}
            return bool(certs and required_keys.issubset(certs.keys()))
        except Exception:
            return False
    
    async def upload_cert_file(self, empresa_id, filename, file_bytes):
        return await self.file_storage.upload_file(f"{empresa_id}/{filename}", file_bytes)
    
    async def download_cert_file(self, empresa_id, filename):
        return await self.file_storage.download_file(f"{empresa_id}/{filename}")


# ========== IMPLEMENTAÇÕES WRAPPER DOS GATEWAYS ==========

class SicrediGatewayWrapper:
    """Wrapper que implementa a interface SicrediGatewayInterface"""
    
    def __init__(self):
        # Lazy loading das dependências
        self._config_repo = None
        self._cert_service = None
    
    @property
    def config_repo(self):
        if self._config_repo is None:
            self._config_repo = get_config_repository()
        return self._config_repo
    
    @property 
    def cert_service(self):
        if self._cert_service is None:
            self._cert_service = get_certificate_service()
        return self._cert_service
    
    async def create_pix_payment(self, empresa_id: str, **kwargs):
        # Import local para evitar circular
        from .services.gateways.sicredi_client import create_sicredi_pix_payment
        return await create_sicredi_pix_payment(
            empresa_id, 
            config_repo=self.config_repo,
            cert_service=self.cert_service,
            **kwargs
        )
    
    async def create_pix_refund(self, empresa_id: str, txid: str, amount=None):
        from .services.gateways.sicredi_client import create_sicredi_pix_refund
        return await create_sicredi_pix_refund(
            empresa_id, 
            txid, 
            amount,
            config_repo=self.config_repo,
            cert_service=self.cert_service
        )
    
    async def get_access_token(self, empresa_id: str):
        from .services.gateways.sicredi_client import get_access_token
        return await get_access_token(
            empresa_id,
            config_repo=self.config_repo,
            cert_service=self.cert_service
        )
    
    async def register_webhook(self, empresa_id: str, chave_pix: str):
        from .services.gateways.sicredi_client import register_sicredi_webhook
        return await register_sicredi_webhook(
            empresa_id,
            chave_pix,
            config_repo=self.config_repo,
            cert_service=self.cert_service
        )


class RedeGatewayWrapper:
    """Wrapper que implementa a interface RedeGatewayInterface"""
    async def create_payment(self, empresa_id: str, **kwargs):
        from .services.gateways.rede_client import create_rede_payment
        return await create_rede_payment(empresa_id, **kwargs)
    
    async def create_refund(self, empresa_id: str, transaction_id: str, amount=None):
        from .services.gateways.rede_client import create_rede_refund
        return await create_rede_refund(empresa_id, transaction_id, amount)
    
    async def tokenize_card(self, empresa_id: str, card_data):
        from .services.gateways.rede_client import tokenize_rede_card
        return await tokenize_rede_card(empresa_id, card_data)
    
    async def capture_transaction(self, empresa_id: str, transaction_id: str, amount=None):
        from .services.gateways.rede_client import capture_rede_transaction
        return await capture_rede_transaction(empresa_id, transaction_id, amount)
    
    async def get_transaction(self, empresa_id: str, transaction_id: str):
        from .services.gateways.rede_client import get_rede_transaction
        return await get_rede_transaction(empresa_id, transaction_id)


class AsaasGatewayWrapper:
    """Wrapper que implementa a interface AsaasGatewayInterface"""
    async def create_payment(self, empresa_id: str, amount: float, payment_type: str, 
                           transaction_id: str, customer_data, **kwargs):
        from .services.gateways.asaas_client import create_asaas_payment
        return await create_asaas_payment(empresa_id, amount, payment_type, 
                                        transaction_id, customer_data, **kwargs)
    
    async def create_refund(self, empresa_id: str, transaction_id: str):
        from .services.gateways.asaas_client import create_asaas_refund
        return await create_asaas_refund(empresa_id, transaction_id)
    
    async def tokenize_card(self, empresa_id: str, card_data):
        from .services.gateways.asaas_client import tokenize_asaas_card
        return await tokenize_asaas_card(empresa_id, card_data)
    
    async def get_payment_status(self, empresa_id: str, transaction_id: str):
        from .services.gateways.asaas_client import get_asaas_payment_status
        return await get_asaas_payment_status(empresa_id, transaction_id)
    
    async def get_pix_qr_code(self, empresa_id: str, payment_id: str):
        from .services.gateways.asaas_client import get_asaas_pix_qr_code
        return await get_asaas_pix_qr_code(empresa_id, payment_id)
    
    async def list_pix_keys(self, empresa_id: str):
        from .services.gateways.asaas_client import list_asaas_pix_keys
        return await list_asaas_pix_keys(empresa_id)
    
    async def validate_pix_key(self, empresa_id: str, chave_pix: str):
        from .services.gateways.asaas_client import validate_asaas_pix_key
        return await validate_asaas_pix_key(empresa_id, chave_pix)


class WebhookServiceWrapper:
    """Wrapper que implementa a interface WebhookServiceInterface"""
    async def notify_user_webhook(self, webhook_url: str, data):
        return await notify_user_webhook(webhook_url, data)
    
    async def process_webhook(self, provider: str, payload):
        # Implementação básica - pode ser expandida
        return True


# ========== DEPENDENCY INJECTION COM CACHE ==========

@lru_cache(maxsize=1)
def get_payment_repository() -> PaymentRepositoryInterface:
    """Retorna implementação de PaymentRepository com cache"""
    if _repositories_available:
        return PaymentRepository()
    else:
        print("⚠️ Usando DummyPaymentRepository")
        return DummyPaymentRepository()

@lru_cache(maxsize=1)
def get_customer_repository() -> CustomerRepositoryInterface:
    """Retorna implementação de CustomerRepository com cache"""
    if _customer_repository_available:
        return CustomerRepository()
    else:
        print("⚠️ Usando DummyCustomerRepository")
        return DummyCustomerRepository()

@lru_cache(maxsize=1)
def get_config_repository() -> ConfigRepositoryInterface:
    """Retorna implementação de ConfigRepository com cache"""
    if _repositories_available:
        return ConfigRepository()
    else:
        print("⚠️ Usando DummyConfigRepository")
        return DummyConfigRepository()

@lru_cache(maxsize=1)
def get_card_repository() -> CardRepositoryInterface:
    """Retorna implementação de CardRepository com cache"""
    if _repositories_available:
        return CardRepository()
    else:
        print("⚠️ Usando DummyCardRepository")
        return DummyCardRepository()

@lru_cache(maxsize=1)
def get_asaas_customer_repository() -> AsaasCustomerInterface:
    """Retorna implementação de AsaasCustomerRepository com cache"""
    if _repositories_available:
        return AsaasCustomerRepository()
    else:
        print("⚠️ Usando DummyAsaasCustomerRepository")
        return DummyAsaasCustomerRepository()

@lru_cache(maxsize=1)
def get_customer_service() -> CustomerServiceInterface:
    """Retorna implementação de CustomerService com cache"""
    if _customer_repository_available:
        return CustomerService()
    else:
        print("⚠️ Usando DummyCustomerService")
        return DummyCustomerService()

@lru_cache(maxsize=1)
def get_payment_validator() -> PaymentValidatorInterface:
    """Retorna implementação de PaymentValidator com cache"""
    if _validators_available:
        return PaymentValidator()
    else:
        print("⚠️ Usando DummyPaymentValidator")
        return DummyPaymentValidator()

@lru_cache(maxsize=1)
def get_sicredi_gateway() -> SicrediGatewayInterface:
    """Retorna implementação de Sicredi Gateway com cache"""
    try:
        return SicrediGatewayWrapper()
    except Exception:
        print("⚠️ Usando DummySicrediGateway")
        return DummySicrediGateway()

@lru_cache(maxsize=1)
def get_rede_gateway() -> RedeGatewayInterface:
    """Retorna implementação de Rede Gateway com cache"""
    try:
        return RedeGatewayWrapper()
    except Exception:
        print("⚠️ Usando DummyRedeGateway")
        return DummyRedeGateway()

@lru_cache(maxsize=1)
def get_asaas_gateway() -> AsaasGatewayInterface:
    """Retorna implementação de Asaas Gateway com cache"""
    try:
        return AsaasGatewayWrapper()
    except Exception:
        print("⚠️ Usando DummyAsaasGateway")
        return DummyAsaasGateway()

@lru_cache(maxsize=1)
def get_webhook_service() -> WebhookServiceInterface:
    """Retorna implementação de Webhook Service com cache"""
    if _webhook_available:
        return WebhookServiceWrapper()
    else:
        print("⚠️ Usando DummyWebhookService")
        return DummyWebhookService()

@lru_cache(maxsize=1)
def get_certificate_service() -> CertificateServiceInterface:
    """Retorna implementação de Certificate Service com cache"""
    if _config_service_available and _file_storage_available:
        return CertificateServiceImplementation()
    else:
        print("⚠️ Usando DummyCertificateService")
        return DummyCertificateService()

@lru_cache(maxsize=1)
def get_empresa_repository() -> EmpresaRepositoryInterface:
    """Retorna implementação de EmpresaRepository com cache"""
    if _empresa_repository_available:
        return EmpresaRepository()
    else:
        print("⚠️ Usando DummyEmpresaRepository")
        return DummyEmpresaRepository()

@lru_cache(maxsize=1)
def get_file_storage() -> FileStorageInterface:
    """Retorna implementação de FileStorage com cache"""
    if _file_storage_available:
        return FileStorageRepository()
    else:
        print("⚠️ Usando DummyFileStorage")
        return DummyFileStorage()

@lru_cache(maxsize=1)
def get_cache_repository() -> CacheRepositoryInterface:
    """Retorna implementação de CacheRepository com cache"""
    # Por enquanto, sempre dummy até implementarmos Redis
    print("⚠️ Usando DummyCacheRepository - Redis não implementado ainda")
    return DummyCacheRepository()

# ========== DEPENDENCY INJECTION SEM CACHE (PARA TESTES) ==========

def get_payment_repository_fresh() -> PaymentRepositoryInterface:
    """Retorna nova instância de PaymentRepository (sem cache)"""
    if _repositories_available:
        return PaymentRepository()
    return DummyPaymentRepository()

def get_customer_repository_fresh() -> CustomerRepositoryInterface:
    """Retorna nova instância de CustomerRepository (sem cache)"""
    if _customer_repository_available:
        return CustomerRepository()
    return DummyCustomerRepository()

def get_config_repository_fresh() -> ConfigRepositoryInterface:
    """Retorna nova instância de ConfigRepository (sem cache)"""
    if _repositories_available:
        return ConfigRepository()
    return DummyConfigRepository()

def get_card_repository_fresh() -> CardRepositoryInterface:
    """Retorna nova instância de CardRepository (sem cache)"""
    if _repositories_available:
        return CardRepository()
    return DummyCardRepository()

def get_customer_service_fresh() -> CustomerServiceInterface:
    """Retorna nova instância de CustomerService (sem cache)"""
    if _customer_repository_available:
        return CustomerService()
    return DummyCustomerService()

def get_payment_validator_fresh() -> PaymentValidatorInterface:
    """Retorna nova instância de PaymentValidator (sem cache)"""
    if _validators_available:
        return PaymentValidator()
    return DummyPaymentValidator()

def get_empresa_repository_fresh() -> EmpresaRepositoryInterface:
    """Retorna nova instância de EmpresaRepository (sem cache)"""
    if _empresa_repository_available:
        return EmpresaRepository()
    return DummyEmpresaRepository()

def get_file_storage_fresh() -> FileStorageInterface:
    """Retorna nova instância de FileStorage (sem cache)"""
    if _file_storage_available:
        return FileStorageRepository()
    return DummyFileStorage()

def get_certificate_service_fresh() -> CertificateServiceInterface:
    """Retorna nova instância de CertificateService (sem cache)"""
    if _config_service_available and _file_storage_available:
        return CertificateServiceImplementation()
    return DummyCertificateService()

# ========== UTILITÁRIOS DE DIAGNÓSTICO ==========

def check_dependencies_health() -> dict:
    """Verifica se todas as dependências estão disponíveis"""
    return {
        "repositories_available": _repositories_available,
        "customer_repository_available": _customer_repository_available, 
        "validators_available": _validators_available,
        "empresa_repository_available": _empresa_repository_available,
        "file_storage_available": _file_storage_available,
        "webhook_available": _webhook_available,
        "config_service_available": _config_service_available,
        "all_core_available": all([
            _repositories_available,
            _customer_repository_available,
            _validators_available,
            _empresa_repository_available
        ]),
        "all_gateways_available": True,  # Simplificado
        "all_services_available": all([
            _webhook_available,
            _config_service_available,
            _file_storage_available
        ])
    }

def clear_dependency_cache():
    """Limpa o cache das dependências"""
    get_payment_repository.cache_clear()
    get_customer_repository.cache_clear()
    get_config_repository.cache_clear()
    get_card_repository.cache_clear()
    get_asaas_customer_repository.cache_clear()
    get_customer_service.cache_clear()
    get_payment_validator.cache_clear()
    get_sicredi_gateway.cache_clear()
    get_rede_gateway.cache_clear()
    get_asaas_gateway.cache_clear()
    get_webhook_service.cache_clear()
    get_empresa_repository.cache_clear()
    get_file_storage.cache_clear()
    get_cache_repository.cache_clear()
    get_certificate_service.cache_clear()
    print("✅ Cache de dependências limpo")

# ========== DEPENDENCY OVERRIDE (PARA TESTES) ==========

_dependency_overrides = {}

def override_dependency(interface_type: type, implementation):
    """Sobrescreve uma dependência para testes"""
    _dependency_overrides[interface_type] = implementation

def get_dependency_override(interface_type: type):
    """Retorna override se existir"""
    return _dependency_overrides.get(interface_type)

def clear_dependency_overrides():
    """Limpa todos os overrides"""
    _dependency_overrides.clear()
    print("✅ Overrides de dependências limpos")

# ========== DEPENDENCY PROVIDERS COM OVERRIDE ==========

def get_payment_repository_with_override() -> PaymentRepositoryInterface:
    """Retorna PaymentRepository considerando overrides"""
    override = get_dependency_override(PaymentRepositoryInterface)
    if override:
        return override
    return get_payment_repository()

def get_customer_repository_with_override() -> CustomerRepositoryInterface:
    """Retorna CustomerRepository considerando overrides"""
    override = get_dependency_override(CustomerRepositoryInterface)
    if override:
        return override
    return get_customer_repository()

def get_config_repository_with_override() -> ConfigRepositoryInterface:
    """Retorna ConfigRepository considerando overrides"""
    override = get_dependency_override(ConfigRepositoryInterface)
    if override:
        return override
    return get_config_repository()

def get_empresa_repository_with_override() -> EmpresaRepositoryInterface:
    """Retorna EmpresaRepository considerando overrides"""
    override = get_dependency_override(EmpresaRepositoryInterface)
    if override:
        return override
    return get_empresa_repository()

def get_certificate_service_with_override() -> CertificateServiceInterface:
    """Retorna CertificateService considerando overrides"""
    override = get_dependency_override(CertificateServiceInterface)
    if override:
        return override
    return get_certificate_service()

# ========== EXPORTS ==========

__all__ = [
    # Dependency providers principais (com cache)
    "get_payment_repository",
    "get_customer_repository", 
    "get_config_repository",
    "get_card_repository",
    "get_asaas_customer_repository",
    "get_customer_service",
    "get_payment_validator",
    
    # Novos providers para gateways e serviços
    "get_sicredi_gateway",
    "get_rede_gateway",
    "get_asaas_gateway",
    "get_webhook_service",
    "get_certificate_service",
    
    # Providers de empresa e storage
    "get_empresa_repository",
    "get_file_storage", 
    "get_cache_repository",
    
    # Dependency providers sem cache (para testes)
    "get_payment_repository_fresh",
    "get_customer_repository_fresh",
    "get_config_repository_fresh", 
    "get_card_repository_fresh",
    "get_customer_service_fresh",
    "get_payment_validator_fresh",
    "get_empresa_repository_fresh",
    "get_file_storage_fresh",
    "get_certificate_service_fresh",
    
    # Dependency providers com override (para testes)
    "get_payment_repository_with_override",
    "get_customer_repository_with_override",
    "get_config_repository_with_override",
    "get_empresa_repository_with_override",
    "get_certificate_service_with_override",
    
    # Utilitários
    "check_dependencies_health",
    "clear_dependency_cache",
    "override_dependency",
    "clear_dependency_overrides",
]