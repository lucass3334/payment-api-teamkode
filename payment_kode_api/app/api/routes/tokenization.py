# payment_kode_api/app/api/routes/tokenization.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import uuid
import re

from payment_kode_api.app.database.database import (
    save_tokenized_card, get_tokenized_card, delete_tokenized_card
)
from payment_kode_api.app.security.crypto import encrypt_card_data
from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.utilities.logging_config import logger

# Imports para gestão de clientes
from payment_kode_api.app.database.customers_management import (
    get_or_create_cliente, 
    extract_customer_data_from_payment,
    get_cliente_by_external_id,
    get_cliente_by_id
)

router = APIRouter()


class TokenizeCardRequest(BaseModel):
    """Schema atualizado para tokenização com customer_id OPCIONAL e criação automática."""
    
    # ========== DADOS DO CARTÃO (OBRIGATÓRIOS) ==========
    card_number: str
    expiration_month: str
    expiration_year: str
    security_code: str
    cardholder_name: str
    
    # ========== DADOS DO CLIENTE (TODOS OPCIONAIS) ==========
    customer_id: Optional[str] = None  # ID externo customizado (OPCIONAL)
    customer_name: Optional[str] = None  # Se não fornecido, usa cardholder_name
    customer_email: Optional[EmailStr] = None
    customer_cpf_cnpj: Optional[str] = None
    customer_phone: Optional[str] = None
    
    # ========== DADOS DE ENDEREÇO (OPCIONAIS) ==========
    customer_cep: Optional[str] = None
    customer_logradouro: Optional[str] = None
    customer_numero: Optional[str] = None
    customer_complemento: Optional[str] = None
    customer_bairro: Optional[str] = None
    customer_cidade: Optional[str] = None
    customer_estado: Optional[str] = None
    customer_pais: Optional[str] = "Brasil"
    
    @field_validator('customer_cpf_cnpj', mode='before')
    @classmethod
    def validate_cpf_cnpj(cls, v):
        """Remove formatação de CPF/CNPJ."""
        if v:
            return re.sub(r'[^0-9]', '', str(v))
        return v
    
    @field_validator('customer_cep', mode='before')
    @classmethod
    def validate_cep(cls, v):
        """Remove formatação do CEP e valida."""
        if v:
            v = re.sub(r'[^0-9]', '', str(v))
            if len(v) != 8:
                raise ValueError("CEP deve ter 8 dígitos")
        return v
    
    @field_validator('customer_estado', mode='before')
    @classmethod
    def validate_estado(cls, v):
        """Converte estado para uppercase."""
        if v:
            return str(v).upper()
        return v


class TokenizedCardResponse(BaseModel):
    """Resposta da tokenização com dados do cliente."""
    card_token: str
    customer_internal_id: Optional[str] = None  # UUID interno (pode ser None)
    customer_external_id: Optional[str] = None  # ID externo (pode ser None)
    customer_created: bool = False  # Indica se cliente foi criado agora
    expires_at: Optional[str] = None


@router.post("/tokenize-card", response_model=TokenizedCardResponse)
async def tokenize_card(
    card_data: TokenizeCardRequest,
    empresa: dict = Depends(validate_access_token)
):
    """
    🔧 CORRIGIDO: Tokeniza cartão com criação automática de cliente OPCIONAL.
    
    Comportamento:
    1. Se dados suficientes do cliente fornecidos → cria/busca cliente
    2. Se apenas dados do cartão → tokeniza sem vincular cliente
    3. customer_id é completamente opcional
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        logger.info(f"🔐 Iniciando tokenização para empresa {empresa_id}")
        
        # ========== 1. GERAR TOKEN DO CARTÃO ==========
        card_token = str(uuid.uuid4())
        
        # ========== 2. CRIPTOGRAFAR DADOS DO CARTÃO ==========
        encrypted_card_data = await encrypt_card_data(empresa_id, {
            "card_number": card_data.card_number,
            "expiration_month": card_data.expiration_month,
            "expiration_year": card_data.expiration_year,
            "security_code": card_data.security_code,
            "cardholder_name": card_data.cardholder_name
        })
        
        # ========== 3. DETECTAR BANDEIRA DO CARTÃO ==========
        card_brand = detect_card_brand(card_data.card_number)
        
        # ========== 4. PROCESSAR CLIENTE (OPCIONAL) ==========
        cliente_uuid = None
        customer_external_id = None
        customer_created = False
        
        # Verificar se temos dados suficientes para criar/buscar cliente
        has_customer_data = any([
            card_data.customer_id,
            card_data.customer_name,
            card_data.customer_email,
            card_data.customer_cpf_cnpj,
            card_data.customer_phone
        ])
        
        if has_customer_data:
            try:
                # Extrair dados do cliente
                customer_payload = extract_customer_data_from_payment(card_data.dict())
                
                # Se não tem nome do cliente, usar nome do portador do cartão
                if not customer_payload.get("nome"):
                    customer_payload["nome"] = card_data.cardholder_name
                
                # Verificar se tem dados mínimos para criar cliente
                if customer_payload.get("nome"):
                    # Buscar cliente existente primeiro (se customer_id fornecido)
                    if card_data.customer_id:
                        existing_cliente = await get_cliente_by_external_id(empresa_id, card_data.customer_id)
                        if existing_cliente:
                            cliente_uuid = existing_cliente["id"]
                            customer_external_id = existing_cliente.get("customer_external_id")
                            logger.info(f"✅ Cliente existente encontrado: {card_data.customer_id}")
                    
                    # Se não encontrou cliente existente, criar novo
                    if not cliente_uuid:
                        cliente_uuid = await get_or_create_cliente(empresa_id, customer_payload)
                        customer_created = True
                        
                        # Buscar dados completos do cliente criado
                        cliente = await get_cliente_by_id(cliente_uuid)
                        if cliente:
                            customer_external_id = cliente.get("customer_external_id")
                        
                        logger.info(f"✅ Novo cliente criado: UUID {cliente_uuid}, External ID: {customer_external_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar cliente (continuando tokenização sem cliente): {e}")
                # Continua a tokenização mesmo se falhar na criação do cliente
        
        # ========== 5. SALVAR CARTÃO TOKENIZADO ==========
        tokenized_card_data = {
            "empresa_id": empresa_id,
            "customer_id": customer_external_id,  # ID externo para compatibilidade
            "card_token": card_token,
            "encrypted_card_data": encrypted_card_data,
            "last_four_digits": card_data.card_number[-4:],
            "card_brand": card_brand,
            "cliente_id": cliente_uuid  # UUID interno para relacionamento
        }

        await save_tokenized_card(tokenized_card_data)
        
        logger.info(f"✅ Cartão tokenizado com sucesso: {card_token}")
        
        return TokenizedCardResponse(
            card_token=card_token,
            customer_internal_id=cliente_uuid,
            customer_external_id=customer_external_id,
            customer_created=customer_created,
            expires_at=None  # Implementar expiração se necessário
        )
        
    except Exception as e:
        logger.error(f"❌ Erro na tokenização para empresa {empresa_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno na tokenização: {str(e)}")


def detect_card_brand(card_number: str) -> str:
    """
    Detecta a bandeira do cartão baseado no número.
    """
    # Remove espaços e caracteres não numéricos
    clean_number = re.sub(r'[^0-9]', '', card_number)
    
    if clean_number.startswith('4'):
        return 'VISA'
    elif clean_number.startswith('5') or clean_number.startswith('2'):
        return 'MASTERCARD'
    elif clean_number.startswith('3'):
        return 'AMEX'
    elif clean_number.startswith('6'):
        return 'DISCOVER'
    else:
        return 'UNKNOWN'


@router.get("/tokenize-card/{card_token}")
async def get_tokenized_card_route(
    card_token: str, 
    empresa: dict = Depends(validate_access_token)
):
    """
    🔧 CORRIGIDO: Recupera dados de cartão tokenizado com informações do cliente.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        card = await get_tokenized_card(card_token)
        
        if not card or card["empresa_id"] != empresa_id:
            raise HTTPException(
                status_code=404, 
                detail="Token de cartão inválido ou não encontrado."
            )
        
        # Buscar dados do cliente se existir
        cliente_info = None
        if card.get("cliente_id"):  # UUID interno
            cliente = await get_cliente_by_id(card["cliente_id"])
            if cliente:
                cliente_info = {
                    "customer_external_id": cliente.get("customer_external_id"),
                    "nome": cliente.get("nome"),
                    "email": cliente.get("email")
                }
        
        # Remove dados sensíveis da resposta
        safe_card = {
            "card_token": card["card_token"],
            "customer_internal_id": card.get("cliente_id"),
            "customer_external_id": card.get("customer_id"),  # Para compatibilidade
            "last_four_digits": card.get("last_four_digits"),
            "card_brand": card.get("card_brand"),
            "created_at": card.get("created_at"),
            "expires_at": card.get("expires_at"),
            "cliente_info": cliente_info
        }
        
        return safe_card
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartão tokenizado {card_token}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar cartão.")


@router.delete("/tokenize-card/{card_token}")
async def delete_tokenized_card_route(
    card_token: str, 
    empresa: dict = Depends(validate_access_token)
):
    """
    Remove um cartão tokenizado do sistema.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        card = await get_tokenized_card(card_token)
        
        if not card:
            raise HTTPException(
                status_code=404,
                detail="Cartão não encontrado"
            )
        
        if card["empresa_id"] != empresa_id:
            raise HTTPException(
                status_code=403, 
                detail="Não autorizado a deletar este cartão"
            )
        
        await delete_tokenized_card(card_token)
        
        logger.info(f"✅ Cartão {card_token} removido com sucesso (empresa: {empresa_id})")
        
        return {"message": f"Cartão tokenizado {card_token} removido com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao remover cartão {card_token}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao remover cartão.")


# ========== ENDPOINTS ESPECÍFICOS POR CLIENTE ==========

@router.get("/customer/{customer_uuid}/cards")
async def list_customer_cards_by_uuid(
    customer_uuid: str,
    empresa: dict = Depends(validate_access_token)
):
    """
    Lista cartões tokenizados de um cliente específico (usando UUID interno).
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        from payment_kode_api.app.database.supabase_client import supabase
        
        # Verificar se cliente pertence à empresa
        cliente = await get_cliente_by_id(customer_uuid)
        if not cliente or cliente["empresa_id"] != empresa_id:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        response = (
            supabase.table("cartoes_tokenizados")
            .select("card_token, last_four_digits, card_brand, created_at, expires_at")
            .eq("empresa_id", empresa_id)
            .eq("cliente_id", customer_uuid)  # Usando cliente_id (UUID)
            .order("created_at", desc=True)
            .execute()
        )
        
        cards = response.data or []
        
        logger.info(f"📋 Listando {len(cards)} cartões para cliente {customer_uuid}")
        
        return {
            "customer_internal_id": customer_uuid,
            "customer_external_id": cliente.get("customer_external_id"),
            "customer_name": cliente.get("nome"),
            "cards": cards,
            "total": len(cards)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao listar cartões do cliente {customer_uuid}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao listar cartões.")


@router.get("/customer/external/{external_id}/cards")
async def list_customer_cards_by_external_id(
    external_id: str,
    empresa: dict = Depends(validate_access_token)
):
    """
    Lista cartões tokenizados de um cliente usando o ID externo.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Buscar cliente pelo ID externo
        cliente = await get_cliente_by_external_id(empresa_id, external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Usar o UUID interno para buscar cartões
        return await list_customer_cards_by_uuid(cliente["id"], {"empresa_id": empresa_id})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao listar cartões do cliente externo {external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao listar cartões.")


@router.post("/customer/{customer_external_id}/tokenize-card", response_model=TokenizedCardResponse)
async def tokenize_card_for_customer(
    customer_external_id: str,
    card_data: TokenizeCardRequest,
    empresa: dict = Depends(validate_access_token)
):
    """
    🆕 NOVO: Tokeniza um cartão diretamente para um cliente específico.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Verificar se cliente existe
        cliente = await get_cliente_by_external_id(empresa_id, customer_external_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        # Definir o customer_id no card_data
        card_data.customer_id = customer_external_id
        
        # Usar a função principal de tokenização
        result = await tokenize_card(card_data, empresa)
        
        logger.info(f"✅ Cartão tokenizado para cliente específico: {customer_external_id}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao tokenizar cartão para cliente {customer_external_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno na tokenização.")


@router.get("/stats")
async def get_tokenization_stats(
    empresa: dict = Depends(validate_access_token)
):
    """
    🆕 NOVO: Retorna estatísticas de tokenização da empresa.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        from payment_kode_api.app.database.supabase_client import supabase
        from datetime import datetime, timedelta
        
        # Total de cartões tokenizados
        total_response = (
            supabase.table("cartoes_tokenizados")
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        
        total_cards = total_response.count or 0
        
        # Cartões por bandeira
        brands_response = (
            supabase.table("cartoes_tokenizados")
            .select("card_brand")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        
        brands_count = {}
        for card in (brands_response.data or []):
            brand = card.get("card_brand", "UNKNOWN")
            brands_count[brand] = brands_count.get(brand, 0) + 1
        
        # Cartões criados nos últimos 30 dias
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        recent_response = (
            supabase.table("cartoes_tokenizados")
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .gte("created_at", thirty_days_ago)
            .execute()
        )
        
        recent_cards = recent_response.count or 0
        
        # Cartões com cliente vs sem cliente
        with_customer_response = (
            supabase.table("cartoes_tokenizados")
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .not_.is_("cliente_id", "null")
            .execute()
        )
        
        cards_with_customer = with_customer_response.count or 0
        cards_without_customer = total_cards - cards_with_customer
        
        return {
            "total_cards": total_cards,
            "recent_cards_30_days": recent_cards,
            "cards_by_brand": brands_count,
            "most_used_brand": max(brands_count.items(), key=lambda x: x[1])[0] if brands_count else None,
            "cards_with_customer": cards_with_customer,
            "cards_without_customer": cards_without_customer,
            "customer_linkage_rate": round((cards_with_customer / total_cards * 100), 1) if total_cards > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas de tokenização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao obter estatísticas.")