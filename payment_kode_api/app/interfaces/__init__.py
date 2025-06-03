# payment_kode_api/app/interfaces/__init__.py

from typing import Protocol, Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime


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


class CardRepositoryInterface(Protocol):
    """Interface para operações de cartões tokenizados"""
    
    async def save_tokenized_card(self, card_data: Dict[str, Any]) -> Dict[str, Any]: ...
    
    async def get_tokenized_card(self, card_token: str) -> Optional[Dict[str, Any]]: ...
    
    async def delete_tokenized_card(self, card_token: str) -> bool: ...


class ConfigRepositoryInterface(Protocol):
    """Interface para configurações de empresa"""
    
    async def get_empresa_config(self, empresa_id: str) -> Optional[Dict[str, Any]]: ...
    
    async def get_sicredi_token_or_refresh(self, empresa_id: str) -> str: ...


class CustomerServiceInterface(Protocol):
    """Interface para serviços de cliente"""
    
    def extract_customer_data_from_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]: ...


class PaymentValidatorInterface(Protocol):
    """Interface para validações de pagamento"""
    
    def validate_installments_by_gateway(
        self, 
        installments: int, 
        gateway: str, 
        amount: Decimal
    ) -> int: ...


class AsaasCustomerInterface(Protocol):
    """Interface para gestão de clientes Asaas"""
    
    async def get_asaas_customer(self, empresa_id: str, local_customer_id: str) -> Optional[str]: ...


# ========== INTERFACES DE GATEWAY (opcionais, para futuro) ==========

class PaymentGatewayInterface(Protocol):
    """Interface base para gateways de pagamento"""
    
    async def process_payment(self, **kwargs) -> Dict[str, Any]: ...
    
    async def get_payment_status(self, transaction_id: str) -> Dict[str, Any]: ...


# ========== EXPORTS ==========

__all__ = [
    # Repositórios principais
    "PaymentRepositoryInterface",
    "CustomerRepositoryInterface", 
    "CardRepositoryInterface",
    "ConfigRepositoryInterface",
    
    # Serviços
    "CustomerServiceInterface",
    "PaymentValidatorInterface",
    "AsaasCustomerInterface",
    
    # Gateway (opcional)
    "PaymentGatewayInterface",
]