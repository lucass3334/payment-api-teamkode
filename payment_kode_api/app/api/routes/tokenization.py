# payment_kode_api/app/api/routes/tokenization.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import uuid
import re
import json

from payment_kode_api.app.security.auth import validate_access_token
from payment_kode_api.app.utilities.logging_config import logger

# ✅ MANTIDO: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    CustomerRepositoryInterface,
    CustomerServiceInterface,
    CardRepositoryInterface,
)

# ✅ MANTIDO: Dependency injection
from ...dependencies import (
    get_customer_repository,
    get_customer_service,
    get_card_repository,
)

# ✅ CORRIGIDO: Import direto do serviço de tokenização
from ...services.card_tokenization_service import CardTokenizationService

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
    empresa: dict = Depends(validate_access_token),
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    customer_service: CustomerServiceInterface = Depends(get_customer_service),
    card_repo: CardRepositoryInterface = Depends(get_card_repository)
):
    """
    🔧 CORRIGIDO: Usa novo serviço de tokenização sem dependência de RSA.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        logger.info(f"🔐 Iniciando tokenização para empresa {empresa_id}")
        
        # ========== 1. CRIAR TOKEN SEGURO (NOVO) - SEM RSA ==========
        tokenization_service = CardTokenizationService()
        
        token_data = tokenization_service.create_card_token(empresa_id, {
            "card_number": card_data.card_number,
            "expiration_month": card_data.expiration_month,
            "expiration_year": card_data.expiration_year,
            "security_code": card_data.security_code,
            "cardholder_name": card_data.cardholder_name
        })
        
        card_token = token_data["card_token"]
        
        # ========== 2. PROCESSAR CLIENTE (OPCIONAL) - ✅ USANDO INTERFACES ==========
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
                # Extrair dados do cliente - ✅ USANDO INTERFACE
                customer_payload = customer_service.extract_customer_data_from_payment(card_data.dict())
                
                # Se não tem nome do cliente, usar nome do portador do cartão
                if not customer_payload.get("nome"):
                    customer_payload["nome"] = card_data.cardholder_name
                
                # Verificar se tem dados mínimos para criar cliente
                if customer_payload.get("nome"):
                    # Buscar cliente existente primeiro (se customer_id fornecido)
                    if card_data.customer_id:
                        # ✅ USANDO INTERFACE
                        existing_cliente = await customer_repo.get_cliente_by_external_id(empresa_id, card_data.customer_id)
                        if existing_cliente:
                            cliente_uuid = existing_cliente["id"]
                            customer_external_id = existing_cliente.get("customer_external_id")
                            logger.info(f"✅ Cliente existente encontrado: {card_data.customer_id}")
                    
                    # Se não encontrou cliente existente, criar novo
                    if not cliente_uuid:
                        # ✅ USANDO INTERFACE
                        cliente_uuid = await customer_repo.get_or_create_cliente(empresa_id, customer_payload)
                        customer_created = True
                        
                        # Buscar dados completos do cliente criado - ✅ USANDO INTERFACE
                        cliente = await customer_repo.get_cliente_by_id(cliente_uuid)
                        if cliente:
                            customer_external_id = cliente.get("customer_external_id")
                        
                        logger.info(f"✅ Novo cliente criado: UUID {cliente_uuid}, External ID: {customer_external_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar cliente (continuando tokenização sem cliente): {e}")
                # Continua a tokenização mesmo se falhar na criação do cliente
        
        # ========== 3. SALVAR NO BANCO (USANDO DADOS SEGUROS) ==========
        # Preparar dados para o banco (SEM encrypted_card_data RSA)
        tokenized_card_data = {
            "empresa_id": empresa_id,
            "customer_id": customer_external_id,
            "card_token": card_token,
            # ✅ NOVO: Usar dados seguros em vez de encrypted_card_data
            "safe_card_data": json.dumps({
                "cardholder_name": token_data["cardholder_name"],
                "last_four_digits": token_data["last_four_digits"],
                "card_brand": token_data["card_brand"],
                "expiration_month": token_data["expiration_month"],
                "expiration_year": token_data["expiration_year"],
                "card_hash": token_data["card_hash"],
                "tokenization_method": "simple_hash_v1"
            }),
            "last_four_digits": token_data["last_four_digits"],
            "card_brand": token_data["card_brand"],
            "expires_at": token_data["expires_at"],
            "cliente_id": cliente_uuid
        }

        await card_repo.save_tokenized_card(tokenized_card_data)
        
        logger.info(f"✅ Cartão tokenizado com sucesso: {card_token}")
        
        return TokenizedCardResponse(
            card_token=card_token,
            customer_internal_id=cliente_uuid,
            customer_external_id=customer_external_id,
            customer_created=customer_created,
            expires_at=token_data["expires_at"]
        )
        
    except Exception as e:
        logger.error(f"❌ Erro na tokenização para empresa {empresa_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno na tokenização: {str(e)}")


@router.get("/tokenize-card/{card_token}")
async def get_tokenized_card_route(
    card_token: str, 
    empresa: dict = Depends(validate_access_token),
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    card_repo: CardRepositoryInterface = Depends(get_card_repository)
):
    """
    🔧 ATUALIZADO: Recupera dados de cartão tokenizado com informações do cliente usando interfaces.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # ✅ USANDO INTERFACE
        card = await card_repo.get_tokenized_card(card_token)
        
        if not card or card["empresa_id"] != empresa_id:
            raise HTTPException(
                status_code=404, 
                detail="Token de cartão inválido ou não encontrado."
            )
        
        # Buscar dados do cliente se existir - ✅ USANDO INTERFACE
        cliente_info = None
        if card.get("cliente_id"):  # UUID interno
            cliente = await customer_repo.get_cliente_by_id(card["cliente_id"])
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
    empresa: dict = Depends(validate_access_token),
    card_repo: CardRepositoryInterface = Depends(get_card_repository)
):
    """
    Remove um cartão tokenizado do sistema.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # ✅ USANDO INTERFACE
        card = await card_repo.get_tokenized_card(card_token)
        
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
        
        # ✅ USANDO INTERFACE
        await card_repo.delete_tokenized_card(card_token)
        
        logger.info(f"✅ Cartão {card_token} removido com sucesso (empresa: {empresa_id})")
        
        return {"message": f"Cartão tokenizado {card_token} removido com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao remover cartão {card_token}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao remover cartão.")


# ========== ENDPOINTS DE ESTATÍSTICAS ==========

@router.get("/stats")
async def get_tokenization_stats(
    empresa: dict = Depends(validate_access_token)
):
    """Retorna estatísticas de tokenização da empresa."""
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
            "cards_by_brand": brands_count,
            "most_used_brand": max(brands_count.items(), key=lambda x: x[1])[0] if brands_count else None,
            "cards_with_customer": cards_with_customer,
            "cards_without_customer": cards_without_customer,
            "customer_linkage_rate": round((cards_with_customer / total_cards * 100), 1) if total_cards > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas de tokenização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao obter estatísticas.")