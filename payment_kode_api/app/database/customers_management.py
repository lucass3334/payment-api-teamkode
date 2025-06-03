# payment_kode_api/app/database/customers_management.py
# Gestão completa de clientes adaptada para estrutura existente (clientes + enderecos)

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta  # 🔧 CORRIGIDO: Adicionado timedelta aqui
from .supabase_client import supabase
from ..utilities.logging_config import logger
import uuid
import re


async def get_or_create_cliente(empresa_id: str, customer_data: Dict[str, Any]) -> str:
    """
    Busca ou cria um cliente na tabela clientes + endereço na tabela enderecos.
    Retorna o UUID interno do cliente criado/encontrado.
    
    Prioridade de busca:
    1. customer_external_id (se fornecido)
    2. cpf_cnpj (unique constraint)
    3. email (unique constraint)
    4. criar novo se não encontrar
    """
    try:
        # 1. Extrair e limpar dados do cliente
        customer_external_id = customer_data.get("customer_id")
        cpf_cnpj = extract_cpf_cnpj(customer_data)
        email = customer_data.get("email") or customer_data.get("customer_email")
        nome = extract_nome(customer_data)
        
        if not nome:
            raise ValueError("Nome do cliente é obrigatório para criação")
        
        # 2. Tentar buscar cliente existente (prioridade: external_id > cpf_cnpj > email)
        existing_cliente = None
        
        # Buscar por customer_external_id primeiro
        if customer_external_id:
            existing_cliente = await get_cliente_by_external_id(empresa_id, customer_external_id)
            if existing_cliente:
                logger.info(f"✅ Cliente encontrado por external_id: {customer_external_id}")
        
        # Se não encontrou, buscar por CPF/CNPJ
        if not existing_cliente and cpf_cnpj:
            existing_cliente = await get_cliente_by_cpf_cnpj(cpf_cnpj)
            # Verificar se pertence à mesma empresa
            if existing_cliente and existing_cliente.get("empresa_id") != empresa_id:
                logger.warning(f"⚠️ CPF/CNPJ {cpf_cnpj} pertence a outra empresa")
                existing_cliente = None
        
        # Se não encontrou, buscar por email
        if not existing_cliente and email:
            existing_cliente = await get_cliente_by_email(email)
            # Verificar se pertence à mesma empresa
            if existing_cliente and existing_cliente.get("empresa_id") != empresa_id:
                logger.warning(f"⚠️ Email {email} pertence a outra empresa")
                existing_cliente = None
        
        if existing_cliente:
            logger.info(f"✅ Cliente existente encontrado: UUID {existing_cliente['id']}")
            
            # Atualizar customer_external_id se não tinha e agora foi fornecido
            if customer_external_id and not existing_cliente.get("customer_external_id"):
                await update_cliente(existing_cliente["id"], {"customer_external_id": customer_external_id})
                logger.info(f"✅ Customer external ID atualizado: {customer_external_id}")
            
            # Criar/atualizar endereço se dados fornecidos
            if has_address_data(customer_data):
                await create_or_update_endereco(existing_cliente["id"], customer_data)
            
            return existing_cliente["id"]
        
        # 3. Criar novo cliente
        logger.info(f"🆕 Criando novo cliente: {nome}")
        
        # Gerar customer_external_id se não fornecido
        if not customer_external_id:
            customer_external_id = generate_external_id(cpf_cnpj, email)
        
        cliente_data = {
            "empresa_id": empresa_id,
            "customer_external_id": customer_external_id,
            "nome": nome,
            "email": email,
            "cpf_cnpj": cpf_cnpj,
            "telefone": extract_telefone(customer_data),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Remove campos None/vazios
        cliente_data = {k: v for k, v in cliente_data.items() if v is not None and v != ""}
        
        response = supabase.table("clientes").insert(cliente_data).execute()
        
        if not response.data:
            raise ValueError("Erro ao criar cliente no banco.")
        
        cliente_uuid = response.data[0]["id"]
        logger.info(f"✅ Novo cliente criado: {customer_external_id} (UUID: {cliente_uuid})")
        
        # 4. Criar endereço se dados fornecidos
        if has_address_data(customer_data):
            endereco_id = await create_or_update_endereco(cliente_uuid, customer_data)
            if endereco_id:
                logger.info(f"✅ Endereço criado para cliente: {endereco_id}")
        
        return cliente_uuid
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar/criar cliente para empresa {empresa_id}: {e}")
        raise


async def get_cliente_by_external_id(empresa_id: str, customer_external_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca cliente pelo customer_external_id e empresa_id.
    """
    try:
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("empresa_id", empresa_id)
            .eq("customer_external_id", customer_external_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cliente {customer_external_id} da empresa {empresa_id}: {e}")
        return None


async def get_cliente_by_cpf_cnpj(cpf_cnpj: str) -> Optional[Dict[str, Any]]:
    """
    Busca cliente pelo CPF/CNPJ (unique constraint).
    """
    try:
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("cpf_cnpj", cpf_cnpj)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cliente por CPF/CNPJ {cpf_cnpj}: {e}")
        return None


async def get_cliente_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Busca cliente pelo email (unique constraint).
    """
    try:
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cliente por email {email}: {e}")
        return None


async def get_cliente_by_id(cliente_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca cliente pelo UUID interno, incluindo endereço principal.
    """
    try:
        # Buscar cliente
        cliente_response = (
            supabase.table("clientes")
            .select("*")
            .eq("id", cliente_id)
            .limit(1)
            .execute()
        )
        
        if not cliente_response.data:
            return None
        
        cliente = cliente_response.data[0]
        
        # Buscar endereço principal
        endereco_principal = await get_endereco_principal_cliente(cliente_id)
        cliente["endereco_principal"] = endereco_principal
        
        # Buscar todos os endereços (opcional)
        enderecos = await get_enderecos_cliente(cliente_id)
        cliente["enderecos"] = enderecos
        
        return cliente
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cliente por ID {cliente_id}: {e}")
        return None


async def create_or_update_endereco(cliente_id: str, customer_data: Dict[str, Any]) -> Optional[str]:
    """
    Cria ou atualiza endereço do cliente.
    Sempre cria um novo endereço (histórico de mudanças).
    """
    try:
        # Extrair e validar dados de endereço
        endereco_data = extract_address_data(customer_data)
        
        if not endereco_data:
            logger.debug(f"📍 Dados de endereço insuficientes para cliente {cliente_id}")
            return None
        
        # Validar campos obrigatórios
        required_fields = ["logradouro", "numero", "bairro", "cidade", "estado", "cep"]
        missing_fields = [field for field in required_fields if not endereco_data.get(field)]
        
        if missing_fields:
            logger.warning(f"⚠️ Campos de endereço obrigatórios faltando: {missing_fields}")
            return None
        
        # Preparar dados para inserção
        endereco_insert = {
            "cliente_id": cliente_id,
            **endereco_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Inserir novo endereço
        response = supabase.table("enderecos").insert(endereco_insert).execute()
        
        if response.data:
            endereco_id = response.data[0]["id"]
            logger.info(f"✅ Novo endereço criado para cliente {cliente_id}: {endereco_id}")
            return endereco_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar endereço do cliente {cliente_id}: {e}")
        return None


async def get_enderecos_cliente(cliente_id: str) -> List[Dict[str, Any]]:
    """
    Retorna todos os endereços de um cliente ordenados por data de criação (mais recente primeiro).
    """
    try:
        response = (
            supabase.table("enderecos")
            .select("*")
            .eq("cliente_id", cliente_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"❌ Erro ao buscar endereços do cliente {cliente_id}: {e}")
        return []


async def get_endereco_principal_cliente(cliente_id: str) -> Optional[Dict[str, Any]]:
    """
    Retorna o endereço principal (mais recente) de um cliente.
    """
    try:
        response = (
            supabase.table("enderecos")
            .select("*")
            .eq("cliente_id", cliente_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar endereço principal do cliente {cliente_id}: {e}")
        return None


async def update_cliente(cliente_id: str, updates: Dict[str, Any]) -> bool:
    """
    Atualiza dados de um cliente existente.
    """
    try:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Remove campos None/vazios
        updates = {k: v for k, v in updates.items() if v is not None and v != ""}
        
        if not updates or updates == {"updated_at": updates["updated_at"]}:
            logger.warning(f"⚠️ Nenhum dado válido para atualizar cliente {cliente_id}")
            return False
        
        response = (
            supabase.table("clientes")
            .update(updates)
            .eq("id", cliente_id)
            .execute()
        )
        
        success = bool(response.data)
        if success:
            logger.info(f"✅ Cliente {cliente_id} atualizado com sucesso")
        else:
            logger.warning(f"⚠️ Cliente {cliente_id} não encontrado para atualização")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar cliente {cliente_id}: {e}")
        return False


async def list_clientes_empresa(empresa_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Lista clientes de uma empresa com paginação, incluindo endereço principal.
    """
    try:
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("empresa_id", empresa_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        
        clientes = response.data or []
        
        # Adicionar endereço principal para cada cliente
        for cliente in clientes:
            endereco = await get_endereco_principal_cliente(cliente["id"])
            cliente["endereco_principal"] = endereco
        
        return clientes
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar clientes da empresa {empresa_id}: {e}")
        return []


async def delete_cliente(cliente_id: str) -> bool:
    """
    Remove um cliente do sistema (cascata remove endereços automaticamente).
    """
    try:
        response = (
            supabase.table("clientes")
            .delete()
            .eq("id", cliente_id)
            .execute()
        )
        
        success = bool(response.data)
        if success:
            logger.info(f"✅ Cliente {cliente_id} removido com sucesso (endereços removidos automaticamente)")
        else:
            logger.warning(f"⚠️ Cliente {cliente_id} não encontrado para remoção")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Erro ao remover cliente {cliente_id}: {e}")
        return False


async def search_clientes(
    empresa_id: str, 
    query: str, 
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Busca clientes por nome, email, CPF/CNPJ ou ID externo.
    """
    try:
        # Limpar query
        query_clean = query.strip().lower()
        
        # Buscar em múltiplos campos
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("empresa_id", empresa_id)
            .or_(f"nome.ilike.%{query_clean}%,email.ilike.%{query_clean}%,cpf_cnpj.like.%{query}%,customer_external_id.ilike.%{query_clean}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        clientes = response.data or []
        
        # Adicionar endereço principal
        for cliente in clientes:
            endereco = await get_endereco_principal_cliente(cliente["id"])
            cliente["endereco_principal"] = endereco
        
        return clientes
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar clientes com query '{query}': {e}")
        return []


async def get_cliente_stats_summary(empresa_id: str) -> Dict[str, Any]:
    """
    Retorna estatísticas resumidas de clientes da empresa.
    """
    try:
        # Total de clientes
        clientes_response = (
            supabase.table("clientes")
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        
        total_clientes = clientes_response.count or 0
        
        # Clientes com endereço
        clientes_com_endereco = 0
        if total_clientes > 0:
            endereco_response = (
                supabase.table("enderecos")
                .select("cliente_id", count="exact")
                .execute()
            )
            # Aqui seria necessário fazer um join, simplificando por agora
            clientes_com_endereco = min(endereco_response.count or 0, total_clientes)
        
        # Clientes criados nos últimos 30 dias
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        novos_response = (
            supabase.table("clientes")
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .gte("created_at", thirty_days_ago)
            .execute()
        )
        
        novos_clientes = novos_response.count or 0
        
        return {
            "total_clientes": total_clientes,
            "clientes_com_endereco": clientes_com_endereco,
            "novos_ultimos_30_dias": novos_clientes,
            "percentual_com_endereco": round((clientes_com_endereco / total_clientes * 100), 1) if total_clientes > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas de clientes da empresa {empresa_id}: {e}")
        return {
            "total_clientes": 0,
            "clientes_com_endereco": 0,
            "novos_ultimos_30_dias": 0,
            "percentual_com_endereco": 0
        }


# ========== FUNÇÕES AUXILIARES PRIVADAS ==========

def extract_customer_data_from_payment(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai dados do cliente de um payload de pagamento PIX ou cartão.
    Padroniza os nomes dos campos para uso com get_or_create_cliente.
    """
    customer_data = {}
    
    # Nome do cliente
    nome = (
        payment_data.get("customer_name") or 
        payment_data.get("nome_devedor") or 
        payment_data.get("cardholder_name") or
        payment_data.get("name")
    )
    if nome:
        customer_data["nome"] = nome.strip()
    
    # Email
    email = payment_data.get("customer_email") or payment_data.get("email")
    if email:
        customer_data["email"] = email.strip().lower()
    
    # CPF/CNPJ
    cpf_cnpj = (
        payment_data.get("customer_cpf_cnpj") or 
        payment_data.get("cpf") or 
        payment_data.get("cnpj")
    )
    if cpf_cnpj:
        customer_data["cpf_cnpj"] = re.sub(r'[^0-9]', '', str(cpf_cnpj))
    
    # Telefone
    telefone = payment_data.get("customer_phone") or payment_data.get("phone")
    if telefone:
        customer_data["telefone"] = re.sub(r'[^0-9]', '', str(telefone))
    
    # Customer ID customizado
    customer_id = payment_data.get("customer_id")
    if customer_id:
        customer_data["customer_id"] = str(customer_id).strip()
    
    # Dados de endereço
    address_fields = [
        "customer_cep", "customer_logradouro", "customer_numero", 
        "customer_complemento", "customer_bairro", "customer_cidade", 
        "customer_estado", "customer_pais"
    ]
    
    for field in address_fields:
        value = payment_data.get(field)
        if value:
            # Remove o prefixo "customer_" para o campo do banco
            db_field = field.replace("customer_", "")
            customer_data[db_field] = str(value).strip()
    
    return customer_data


def extract_cpf_cnpj(customer_data: Dict[str, Any]) -> Optional[str]:
    """Extrai e limpa CPF/CNPJ dos dados do cliente."""
    cpf_cnpj = (
        customer_data.get("cpf_cnpj") or 
        customer_data.get("cpf") or 
        customer_data.get("cnpj")
    )
    if cpf_cnpj:
        return re.sub(r'[^0-9]', '', str(cpf_cnpj))
    return None


def extract_nome(customer_data: Dict[str, Any]) -> Optional[str]:
    """Extrai nome do cliente dos dados."""
    nome = (
        customer_data.get("nome") or 
        customer_data.get("customer_name") or 
        customer_data.get("name") or
        customer_data.get("nome_devedor") or
        customer_data.get("cardholder_name")
    )
    return nome.strip() if nome else None


def extract_telefone(customer_data: Dict[str, Any]) -> Optional[str]:
    """Extrai e limpa telefone dos dados do cliente."""
    telefone = (
        customer_data.get("telefone") or 
        customer_data.get("customer_phone") or 
        customer_data.get("phone")
    )
    if telefone:
        return re.sub(r'[^0-9]', '', str(telefone))
    return None


def has_address_data(customer_data: Dict[str, Any]) -> bool:
    """Verifica se os dados contêm informações suficientes de endereço."""
    # Campos mínimos necessários para criar um endereço
    required_fields = ["logradouro", "numero", "cidade", "estado"]
    
    # Verifica campos diretos
    for field in required_fields:
        if customer_data.get(field):
            continue
        # Verifica campos com prefixo customer_
        if customer_data.get(f"customer_{field}"):
            continue
        return False
    
    return True


def extract_address_data(customer_data: Dict[str, Any]) -> Dict[str, str]:
    """Extrai e limpa dados de endereço."""
    endereco_data = {}
    
    # Mapeamento de campos
    field_mapping = {
        "cep": ["cep", "customer_cep"],
        "logradouro": ["logradouro", "customer_logradouro"],
        "numero": ["numero", "customer_numero"],
        "complemento": ["complemento", "customer_complemento"],
        "bairro": ["bairro", "customer_bairro"],
        "cidade": ["cidade", "customer_cidade"],
        "estado": ["estado", "customer_estado"],
        "pais": ["pais", "customer_pais"]
    }
    
    for db_field, source_fields in field_mapping.items():
        for source_field in source_fields:
            value = customer_data.get(source_field)
            if value:
                if db_field == "cep":
                    endereco_data[db_field] = re.sub(r'[^0-9]', '', str(value))
                elif db_field == "estado":
                    endereco_data[db_field] = str(value).upper().strip()
                else:
                    endereco_data[db_field] = str(value).strip()
                break
    
    # Valor padrão para país
    if not endereco_data.get("pais"):
        endereco_data["pais"] = "Brasil"
    
    return endereco_data


def generate_external_id(cpf_cnpj: Optional[str], email: Optional[str]) -> str:
    """Gera um customer_external_id baseado nos dados disponíveis."""
    if cpf_cnpj:
        return f"doc_{cpf_cnpj}"
    elif email:
        return f"email_{email.split('@')[0]}"
    else:
        return f"auto_{uuid.uuid4().hex[:8]}"


# ========== EXPORTS ==========
__all__ = [
    "get_or_create_cliente",
    "get_cliente_by_external_id",
    "get_cliente_by_cpf_cnpj",
    "get_cliente_by_email",
    "get_cliente_by_id",
    "create_or_update_endereco",
    "get_enderecos_cliente",
    "get_endereco_principal_cliente",
    "update_cliente",
    "list_clientes_empresa",
    "delete_cliente",
    "search_clientes",
    "get_cliente_stats_summary",
    "extract_customer_data_from_payment",
    # Funções auxiliares
    "extract_cpf_cnpj",
    "extract_nome",
    "extract_telefone",
    "has_address_data",
    "extract_address_data",
    "generate_external_id"
]