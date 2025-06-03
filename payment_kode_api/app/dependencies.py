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


# ========== UTILITÁRIOS DE DIAGNÓSTICO ==========

def check_dependencies_health() -> dict:
    """Verifica se todas as dependências estão disponíveis"""
    return {
        "repositories_available": _repositories_available,
        "customer_repository_available": _customer_repository_available, 
        "validators_available": _validators_available,
        "all_available": all([
            _repositories_available,
            _customer_repository_available,
            _validators_available
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


# ========== DEPENDENCY PROVIDERS MELHORADOS ==========

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
    
    # Dependency providers sem cache (para testes)
    "get_payment_repository_fresh",
    "get_customer_repository_fresh",
    "get_config_repository_fresh", 
    "get_card_repository_fresh",
    "get_customer_service_fresh",
    "get_payment_validator_fresh",
    
    # Dependency providers com override (para testes)
    "get_payment_repository_with_override",
    "get_customer_repository_with_override",
    "get_config_repository_with_override",
    
    # Utilitários
    "check_dependencies_health",
    "clear_dependency_cache",
    "override_dependency",
    "clear_dependency_overrides",
]