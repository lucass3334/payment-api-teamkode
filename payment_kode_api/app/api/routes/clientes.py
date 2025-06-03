# payment_kode_api/app/api/routes/clientes.py

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Dict, Any
import re

from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.utilities.logging_config import logger

# ✅ NOVO: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    CustomerRepositoryInterface,
    CustomerServiceInterface,
    PaymentRepositoryInterface,
    CardRepositoryInterface,
)

# ✅ NOVO: Dependency injection
from ...dependencies import (
    get_customer_repository,
    get_customer_service,
    get_payment_repository,
    get_card_repository,
)

router = APIRouter()


# ========== SCHEMAS ==========

class EnderecoCreate(BaseModel):
    """Schema para criação/atualização de endereço."""
    cep: str
    logradouro: str
    numero: str
    complemento: Optional[str] = None
    bairro: str
    cidade: str
    estado: str
    pais: str = "Brasil"
    
    @field_validator('cep', mode='before')
    @classmethod
    def validate_cep(cls, v):
        if v:
            v = re.sub(r'[^0-9]', '', str(v))
            if len(v) != 8:
                raise ValueError("CEP deve ter 8 dígitos")
        return v
    
    @field_validator('estado', mode='before')
    @classmethod
    def validate_estado(cls, v):
        if v:
            return str(v).upper()
        return v


class ClienteCreate(BaseModel):
    """Schema para criação de cliente."""
    customer_external_id: Optional[str] = None
    nome: str
    email: Optional[EmailStr] = None
    cpf_cnpj: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[EnderecoCreate] = None
    
    @field_validator('cpf_cnpj', mode='before')
    @classmethod
    def validate_cpf_cnpj(cls, v):
        if v:
            return re.sub(r'[^0-9]', '', str(v))
        return v
    
    @field_validator('telefone', mode='before')
    @classmethod
    def validate_telefone(cls, v):
        if v:
            return re.sub(r'[^0-9]', '', str(v))
        return v


class ClienteUpdate(BaseModel):
    """Schema para atualização de cliente."""
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    
    @field_validator('telefone', mode='before')
    @classmethod
    def validate_telefone(cls, v):
        if v:
            return re.sub(r'[^0-9]', '', str(v))
        return v


class ClienteResponse(BaseModel):
    """Schema de resposta padrão para cliente."""
    customer_external_id: Optional[str]
    nome: str
    email: Optional[str]
    cpf_cnpj: Optional[str]
    telefone: Optional[str]
    created_at: str
    updated_at: str
    endereco_principal: Optional[Dict[str, Any]] = None


# ========== ENDPOINTS ==========

@router.post("/clientes", response_model=Dict[str, Any])
async def create_cliente(
    cliente_data: ClienteCreate,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection das interfaces
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    customer_service: CustomerServiceInterface = Depends(get_customer_service)
):
    """
    Cria um novo cliente para a empresa.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Converter para formato esperado por get_or_create_cliente
        customer_payload = {
            "customer_id": cliente_data.customer_external_id,
            "nome": cliente_data.nome,
            "email": cliente_data.email,
            "cpf_cnpj": cliente_data.cpf_cnpj,
            "telefone": cliente_data.telefone,
        }
        
        # Adicionar dados de endereço se fornecidos
        if cliente_data.endereco:
            endereco_dict = cliente_data.endereco.dict()
            for key, value in endereco_dict.items():
                customer_payload[f"customer_{key}"] = value
        
        # ✅ USANDO INTERFACE
        cliente_uuid = await customer_repo.get_or_create_cliente(empresa_id, customer_payload)
        
        # Buscar dados completos do cliente criado - ✅ USANDO INTERFACE
        cliente_completo = await customer_repo.get_cliente_by_id(cliente_uuid)
        
        if not cliente_completo:
            raise HTTPException(status_code=500, detail="Erro ao recuperar cliente criado")
        
        return {
            "customer_internal_id": cliente_uuid,
            "customer_external_id": cliente_completo.get("customer_external_id"),
            "nome": cliente_completo.get("nome"),
            "email": cliente_completo.get("email"),
            "cpf_cnpj": cliente_completo.get("cpf_cnpj"),
            "telefone": cliente_completo.get("telefone"),
            "created_at": cliente_completo.get("created_at"),
            "endereco_principal": cliente_completo.get("endereco_principal")
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar cliente: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao criar cliente: {str(e)}")


@router.get("/clientes", response_model=Dict[str, Any])
async def list_clientes(
    empresa: dict = Depends(validate_access_token),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Buscar por nome, email, CPF/CNPJ ou ID externo"),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Lista clientes da empresa com paginação opcional e busca.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        if search:
            # Busca com filtro - ✅ USANDO INTERFACE
            clientes = await customer_repo.search_clientes(empresa_id, search, limit)
            total = len(clientes)
        else:
            # Lista paginada - ✅ USANDO INTERFACE
            clientes = await customer_repo.list_clientes_empresa(empresa_id, limit, offset)
            total = len(clientes)  # Simplificado - idealmente deveria fazer count separado
        
        # Limpar dados sensíveis e formatar resposta
        safe_clientes = []
        for cliente in clientes:
            safe_cliente = {
                "customer_external_id": cliente.get("customer_external_id"),
                "nome": cliente.get("nome"),
                "email": cliente.get("email"),
                "cpf_cnpj": cliente.get("cpf_cnpj"),
                "telefone": cliente.get("telefone"),
                "created_at": cliente.get("created_at"),
                "updated_at": cliente.get("updated_at"),
                "endereco_principal": cliente.get("endereco_principal")
            }
            safe_clientes.append(safe_cliente)
        
        return {
            "customers": safe_clientes,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_search": bool(search)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar clientes da empresa {empresa_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao listar clientes")


@router.get("/clientes/{customer_external_id}", response_model=ClienteResponse)
async def get_cliente(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Busca cliente específico pelo ID externo.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        return ClienteResponse(
            customer_external_id=cliente.get("customer_external_id"),
            nome=cliente.get("nome"),
            email=cliente.get("email"),
            cpf_cnpj=cliente.get("cpf_cnpj"),
            telefone=cliente.get("telefone"),
            created_at=cliente.get("created_at"),
            updated_at=cliente.get("updated_at"),
            endereco_principal=cliente.get("endereco_principal")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar cliente")


@router.put("/clientes/{customer_external_id}")
async def update_cliente_route(
    customer_external_id: str,
    cliente_update: ClienteUpdate,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Atualiza dados de um cliente existente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Preparar dados para atualização
        update_data = {}
        if cliente_update.nome is not None:
            update_data["nome"] = cliente_update.nome
        if cliente_update.email is not None:
            update_data["email"] = cliente_update.email
        if cliente_update.telefone is not None:
            update_data["telefone"] = cliente_update.telefone
        
        if not update_data:
            raise HTTPException(status_code=400, detail="Nenhum dado válido para atualização")
        
        # Atualizar - ✅ USANDO INTERFACE
        success = await customer_repo.update_cliente(cliente["id"], update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Erro ao atualizar cliente")
        
        # Retornar dados atualizados - ✅ USANDO INTERFACE
        cliente_atualizado = await customer_repo.get_cliente_by_id(cliente["id"])
        
        return {
            "message": "Cliente atualizado com sucesso",
            "customer_external_id": cliente_atualizado.get("customer_external_id"),
            "updated_fields": list(update_data.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar cliente")


@router.delete("/clientes/{customer_external_id}")
async def delete_cliente_route(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection das interfaces
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository)
):
    """
    Remove um cliente do sistema (cascata remove endereços).
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Verificar se cliente tem pagamentos (opcional - pode bloquear exclusão) - ✅ USANDO INTERFACE
        pagamentos = await payment_repo.get_payments_by_cliente(empresa_id, cliente["id"], limit=1)
        if pagamentos:
            logger.warning(f"⚠️ Tentativa de deletar cliente {customer_external_id} com pagamentos existentes")
            # Você pode decidir se quer bloquear ou permitir
            # raise HTTPException(status_code=400, detail="Cliente possui pagamentos e não pode ser removido")
        
        # Deletar - ✅ USANDO INTERFACE
        success = await customer_repo.delete_cliente(cliente["id"])
        
        if not success:
            raise HTTPException(status_code=500, detail="Erro ao remover cliente")
        
        return {
            "message": f"Cliente {customer_external_id} removido com sucesso",
            "had_payments": len(pagamentos) > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao remover cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao remover cliente")


@router.get("/clientes/{customer_external_id}/pagamentos")
async def get_cliente_pagamentos(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    limit: int = Query(50, ge=1, le=100),
    # ✅ NOVO: Dependency injection das interfaces
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository)
):
    """
    Lista pagamentos de um cliente específico.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Buscar pagamentos - ✅ USANDO INTERFACE
        payments = await payment_repo.get_payments_by_cliente(empresa_id, cliente["id"], limit)
        
        # Remover dados sensíveis
        safe_payments = []
        for payment in payments:
            safe_payment = {
                "transaction_id": payment["transaction_id"],
                "amount": payment["amount"],
                "payment_type": payment["payment_type"],
                "status": payment["status"],
                "created_at": payment["created_at"],
                "updated_at": payment["updated_at"],
                "data_marketing": payment.get("data_marketing"),
                "installments": payment.get("installments", 1)
            }
            safe_payments.append(safe_payment)
        
        return {
            "customer_external_id": customer_external_id,
            "customer_name": cliente.get("nome"),
            "payments": safe_payments,
            "total": len(safe_payments)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamentos do cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar pagamentos")


@router.get("/clientes/{customer_external_id}/cartoes")
async def get_cliente_cartoes(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection das interfaces
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    card_repo: CardRepositoryInterface = Depends(get_card_repository)
):
    """
    Lista cartões tokenizados de um cliente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Buscar cartões 
        # ⚠️ NOTA: get_cards_by_cliente ainda não está na CardRepositoryInterface
        # Por enquanto, usando import direto - deveria ser adicionado à interface
        from payment_kode_api.app.database.database import get_cards_by_cliente
        cards = await get_cards_by_cliente(empresa_id, cliente["id"])
        
        # Remover dados sensíveis
        safe_cards = []
        for card in cards:
            safe_card = {
                "card_token": card.get("card_token"),
                "last_four_digits": card.get("last_four_digits"),
                "card_brand": card.get("card_brand"),
                "created_at": card.get("created_at"),
                "expires_at": card.get("expires_at"),
                "is_expired": card.get("is_expired", False)
            }
            safe_cards.append(safe_card)
        
        return {
            "customer_external_id": customer_external_id,
            "customer_name": cliente.get("nome"),
            "cards": safe_cards,
            "total": len(safe_cards)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartões do cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar cartões")


@router.get("/clientes/{customer_external_id}/estatisticas")
async def get_cliente_estatisticas(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Retorna estatísticas completas de um cliente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Buscar estatísticas
        # ⚠️ NOTA: get_cliente_stats ainda não está nas interfaces
        # Por enquanto, usando import direto - deveria ser adicionado à interface
        from payment_kode_api.app.database.database import get_cliente_stats
        stats = await get_cliente_stats(empresa_id, cliente["id"])
        
        return {
            "customer_external_id": customer_external_id,
            "customer_name": cliente.get("nome"),
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar estatísticas do cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar estatísticas")


@router.get("/clientes/{customer_external_id}/enderecos")
async def get_cliente_enderecos(
    customer_external_id: str,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Lista todos os endereços de um cliente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Buscar endereços - ✅ USANDO INTERFACE
        enderecos = await customer_repo.get_enderecos_cliente(cliente["id"])
        
        return {
            "customer_external_id": customer_external_id,
            "customer_name": cliente.get("nome"),
            "addresses": enderecos,
            "total": len(enderecos)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar endereços do cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar endereços")


@router.post("/clientes/{customer_external_id}/enderecos")
async def create_cliente_endereco(
    customer_external_id: str,
    endereco_data: EnderecoCreate,
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Adiciona um novo endereço para o cliente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente - ✅ USANDO INTERFACE
        cliente = await customer_repo.get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Converter para formato esperado
        endereco_dict = endereco_data.dict()
        customer_data = {}
        for key, value in endereco_dict.items():
            customer_data[f"customer_{key}"] = value
        
        # Criar endereço - ✅ USANDO INTERFACE
        endereco_id = await customer_repo.create_or_update_endereco(cliente["id"], customer_data)
        
        if not endereco_id:
            raise HTTPException(status_code=500, detail="Erro ao criar endereço")
        
        return {
            "message": "Endereço criado com sucesso",
            "endereco_id": endereco_id,
            "customer_external_id": customer_external_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao criar endereço para cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao criar endereço")


@router.get("/estatisticas")
async def get_empresa_estatisticas_clientes(
    empresa: dict = Depends(validate_access_token),
    # ✅ NOVO: Dependency injection da interface
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository)
):
    """
    Retorna estatísticas gerais de clientes da empresa.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # ✅ USANDO INTERFACE
        stats = await customer_repo.get_cliente_stats_summary(empresa_id)
        
        return {
            "empresa_id": empresa_id,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas da empresa {empresa_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao obter estatísticas")