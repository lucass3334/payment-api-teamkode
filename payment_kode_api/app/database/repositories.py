# payment_kode_api/app/database/repositories.py

from typing import Dict, Any, List, Optional
from ..interfaces import (
    PaymentRepositoryInterface, 
    ConfigRepositoryInterface,
    CardRepositoryInterface,
    AsaasCustomerInterface
)

# Importa suas funções existentes do database
from .database import (
    # Pagamentos
    save_payment as db_save_payment,
    get_payment as db_get_payment,
    update_payment_status as db_update_payment_status,
    get_payment_by_txid as db_get_payment_by_txid,
    update_payment_status_by_txid as db_update_payment_status_by_txid,
    get_payments_by_cliente as db_get_payments_by_cliente,
    
    # Configurações
    get_empresa_config as db_get_empresa_config,
    get_sicredi_token_or_refresh as db_get_sicredi_token_or_refresh,
    
    # Cartões
    save_tokenized_card as db_save_tokenized_card,
    get_tokenized_card as db_get_tokenized_card,
    delete_tokenized_card as db_delete_tokenized_card,
)

# Importa funções dos clientes Asaas
from .customers import (
    get_asaas_customer as db_get_asaas_customer,
)


class PaymentRepository:
    """Implementação que usa suas funções existentes de pagamento"""
    
    async def save_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        return await db_save_payment(payment_data)
    
    async def get_payment(self, transaction_id: str, empresa_id: str) -> Optional[Dict[str, Any]]:
        return await db_get_payment(transaction_id, empresa_id)
    
    async def update_payment_status(
        self, 
        transaction_id: str, 
        empresa_id: str, 
        status: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        return await db_update_payment_status(transaction_id, empresa_id, status, extra_data)
    
    async def get_payment_by_txid(self, txid: str) -> Optional[Dict[str, Any]]:
        return await db_get_payment_by_txid(txid)
    
    async def update_payment_status_by_txid(
        self,
        txid: str,
        empresa_id: str, 
        status: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        return await db_update_payment_status_by_txid(txid, empresa_id, status, extra_data)
    
    async def get_payments_by_cliente(
        self, 
        empresa_id: str, 
        cliente_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        return await db_get_payments_by_cliente(empresa_id, cliente_id, limit)


class ConfigRepository:
    """Implementação para configurações de empresa"""
    
    async def get_empresa_config(self, empresa_id: str) -> Optional[Dict[str, Any]]:
        return await db_get_empresa_config(empresa_id)
    
    async def get_sicredi_token_or_refresh(self, empresa_id: str) -> str:
        return await db_get_sicredi_token_or_refresh(empresa_id)


class CardRepository:
    """Implementação para operações de cartões tokenizados"""
    
    async def save_tokenized_card(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        return await db_save_tokenized_card(card_data)
    
    async def get_tokenized_card(self, card_token: str) -> Optional[Dict[str, Any]]:
        return await db_get_tokenized_card(card_token)
    
    async def delete_tokenized_card(self, card_token: str) -> bool:
        return await db_delete_tokenized_card(card_token)


class AsaasCustomerRepository:
    """Implementação para gestão de clientes Asaas"""
    
    async def get_asaas_customer(self, empresa_id: str, local_customer_id: str) -> Optional[str]:
        return await db_get_asaas_customer(empresa_id, local_customer_id)


# ========== EXPORTS ==========

__all__ = [
    "PaymentRepository",
    "ConfigRepository", 
    "CardRepository",
    "AsaasCustomerRepository",
]