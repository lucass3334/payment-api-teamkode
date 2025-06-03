# payment_kode_api/app/database/customer_repository.py

from typing import Dict, Any, Optional, List
from ..interfaces import CustomerRepositoryInterface, CustomerServiceInterface

# Importa suas funções existentes do customers_management
from .customers_management import (
    # Funções principais de cliente
    get_or_create_cliente as db_get_or_create_cliente,
    get_cliente_by_external_id as db_get_cliente_by_external_id,
    get_cliente_by_cpf_cnpj as db_get_cliente_by_cpf_cnpj,
    get_cliente_by_email as db_get_cliente_by_email,
    get_cliente_by_id as db_get_cliente_by_id,
    update_cliente as db_update_cliente,
    delete_cliente as db_delete_cliente,
    list_clientes_empresa as db_list_clientes_empresa,
    search_clientes as db_search_clientes,
    
    # Funções de endereço
    create_or_update_endereco as db_create_or_update_endereco,
    get_enderecos_cliente as db_get_enderecos_cliente,
    get_endereco_principal_cliente as db_get_endereco_principal_cliente,
    
    # Funções de estatísticas
    get_cliente_stats_summary as db_get_cliente_stats_summary,
    
    # Funções de serviço/utilitárias
    extract_customer_data_from_payment as db_extract_customer_data,
    extract_cpf_cnpj as db_extract_cpf_cnpj,
    extract_nome as db_extract_nome,
    extract_telefone as db_extract_telefone,
    has_address_data as db_has_address_data,
    extract_address_data as db_extract_address_data,
    generate_external_id as db_generate_external_id,
)


class CustomerRepository:
    """Implementação completa que usa suas funções existentes de customers_management"""
    
    # ========== MÉTODOS PRINCIPAIS DE CLIENTE ==========
    
    async def get_or_create_cliente(self, empresa_id: str, customer_data: Dict[str, Any]) -> str:
        """Busca ou cria cliente, retorna UUID interno"""
        return await db_get_or_create_cliente(empresa_id, customer_data)
    
    async def get_cliente_by_external_id(self, empresa_id: str, external_id: str) -> Optional[Dict[str, Any]]:
        """Busca cliente pelo ID externo"""
        return await db_get_cliente_by_external_id(empresa_id, external_id)
    
    async def get_cliente_by_id(self, cliente_id: str) -> Optional[Dict[str, Any]]:
        """Busca cliente pelo UUID interno"""
        return await db_get_cliente_by_id(cliente_id)
    
    async def get_cliente_by_cpf_cnpj(self, cpf_cnpj: str) -> Optional[Dict[str, Any]]:
        """Busca cliente pelo CPF/CNPJ"""
        return await db_get_cliente_by_cpf_cnpj(cpf_cnpj)
    
    async def get_cliente_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Busca cliente pelo email"""
        return await db_get_cliente_by_email(email)
    
    async def update_cliente(self, cliente_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza dados de um cliente"""
        return await db_update_cliente(cliente_id, updates)
    
    async def delete_cliente(self, cliente_id: str) -> bool:
        """Remove um cliente do sistema"""
        return await db_delete_cliente(cliente_id)
    
    async def list_clientes_empresa(self, empresa_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lista clientes de uma empresa com paginação"""
        return await db_list_clientes_empresa(empresa_id, limit, offset)
    
    async def search_clientes(self, empresa_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Busca clientes por nome, email, CPF/CNPJ ou ID externo"""
        return await db_search_clientes(empresa_id, query, limit)
    
    # ========== MÉTODOS DE ENDEREÇO ==========
    
    async def create_or_update_endereco(self, cliente_id: str, customer_data: Dict[str, Any]) -> Optional[str]:
        """Cria ou atualiza endereço do cliente"""
        return await db_create_or_update_endereco(cliente_id, customer_data)
    
    async def get_enderecos_cliente(self, cliente_id: str) -> List[Dict[str, Any]]:
        """Retorna todos os endereços de um cliente"""
        return await db_get_enderecos_cliente(cliente_id)
    
    async def get_endereco_principal_cliente(self, cliente_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o endereço principal (mais recente) de um cliente"""
        return await db_get_endereco_principal_cliente(cliente_id)
    
    # ========== MÉTODOS DE ESTATÍSTICAS ==========
    
    async def get_cliente_stats_summary(self, empresa_id: str) -> Dict[str, Any]:
        """Retorna estatísticas resumidas de clientes da empresa"""
        return await db_get_cliente_stats_summary(empresa_id)


class CustomerService:
    """Implementação completa de serviços de cliente"""
    
    # ========== EXTRAÇÃO DE DADOS ==========
    
    def extract_customer_data_from_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai dados do cliente de um payload de pagamento"""
        return db_extract_customer_data(payment_data)
    
    def extract_cpf_cnpj(self, customer_data: Dict[str, Any]) -> Optional[str]:
        """Extrai e limpa CPF/CNPJ dos dados do cliente"""
        return db_extract_cpf_cnpj(customer_data)
    
    def extract_nome(self, customer_data: Dict[str, Any]) -> Optional[str]:
        """Extrai nome do cliente dos dados"""
        return db_extract_nome(customer_data)
    
    def extract_telefone(self, customer_data: Dict[str, Any]) -> Optional[str]:
        """Extrai e limpa telefone dos dados do cliente"""
        return db_extract_telefone(customer_data)
    
    # ========== VALIDAÇÕES E UTILITÁRIOS ==========
    
    def has_address_data(self, customer_data: Dict[str, Any]) -> bool:
        """Verifica se os dados contêm informações suficientes de endereço"""
        return db_has_address_data(customer_data)
    
    def extract_address_data(self, customer_data: Dict[str, Any]) -> Dict[str, str]:
        """Extrai e limpa dados de endereço"""
        return db_extract_address_data(customer_data)
    
    def generate_external_id(self, cpf_cnpj: Optional[str], email: Optional[str]) -> str:
        """Gera um customer_external_id baseado nos dados disponíveis"""
        return db_generate_external_id(cpf_cnpj, email)


# ========== EXPORTS ==========

__all__ = [
    "CustomerRepository",
    "CustomerService",
]