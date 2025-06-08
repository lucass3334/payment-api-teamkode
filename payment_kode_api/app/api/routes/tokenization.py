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

# 🆕 NOVO: Import do serviço de criptografia por empresa
from ...services.company_encryption import CompanyEncryptionService

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
    # 🆕 NOVO: Informações sobre criptografia
    encryption_method: str = "company_key_v1"
    is_internal_token: bool = True


@router.post("/tokenize-card", response_model=TokenizedCardResponse)
async def tokenize_card(
    card_data: TokenizeCardRequest,
    empresa: dict = Depends(validate_access_token),
    customer_repo: CustomerRepositoryInterface = Depends(get_customer_repository),
    customer_service: CustomerServiceInterface = Depends(get_customer_service),
    card_repo: CardRepositoryInterface = Depends(get_card_repository)
):
    """
    🔧 ATUALIZADO: Tokenização agora usa sistema de criptografia por empresa.
    
    Fluxo:
    1. Gera token interno único (UUID)
    2. Criptografa dados do cartão com chave específica da empresa
    3. Cria/busca cliente automaticamente (se dados fornecidos)
    4. Salva token com dados criptografados
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        logger.info(f"🔐 Iniciando tokenização com criptografia por empresa para {empresa_id}")
        
        # ========== 1. GERAR TOKEN INTERNO ÚNICO ==========
        card_token = str(uuid.uuid4())
        
        # ========== 2. CRIPTOGRAFAR DADOS COM CHAVE DA EMPRESA ==========
        encryption_service = CompanyEncryptionService()
        
        # Preparar dados para criptografia
        card_data_dict = {
            "card_number": card_data.card_number,
            "expiration_month": card_data.expiration_month,
            "expiration_year": card_data.expiration_year,
            "security_code": card_data.security_code,
            "cardholder_name": card_data.cardholder_name,
            "tokenized_at": str(uuid.uuid4()),  # Para garantir unicidade
        }
        
        # Obter chave da empresa
        decryption_key = await encryption_service.get_empresa_decryption_key(empresa_id)
        
        # Criptografar dados
        encrypted_card_data = encryption_service.encrypt_card_data_with_company_key(
            card_data_dict, 
            decryption_key
        )
        
        logger.info(f"✅ Dados do cartão criptografados com chave da empresa {empresa_id}")
        
        # ========== 3. PROCESSAR CLIENTE (OPCIONAL) ==========
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
        
        # ========== 4. PREPARAR DADOS SEGUROS PARA O BANCO ==========
        # Detectar bandeira do cartão
        card_brand = detect_card_brand(card_data.card_number)
        last_four_digits = card_data.card_number[-4:]
        
        # Calcular data de expiração do token (2 anos)
        from datetime import datetime, timezone, timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(days=730)).isoformat()
        
        # Dados seguros (sem informações sensíveis)
        safe_card_data = {
            "cardholder_name": card_data.cardholder_name,
            "last_four_digits": last_four_digits,
            "card_brand": card_brand,
            "expiration_month": card_data.expiration_month,
            "expiration_year": card_data.expiration_year,
            "tokenization_method": "company_encryption_v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at
        }
        
        # ========== 5. SALVAR NO BANCO ==========
        tokenized_card_data = {
            "empresa_id": empresa_id,
            "customer_id": customer_external_id,  # ID externo (string)
            "card_token": card_token,
            "encrypted_card_data": encrypted_card_data,  # 🆕 NOVO: Dados criptografados com chave da empresa
            "safe_card_data": json.dumps(safe_card_data),  # 🆕 NOVO: Dados seguros em JSON
            "last_four_digits": last_four_digits,
            "card_brand": card_brand,
            "expires_at": expires_at,
            "cliente_id": cliente_uuid  # UUID interno (se existir)
        }

        await card_repo.save_tokenized_card(tokenized_card_data)
        
        logger.info(f"✅ Cartão tokenizado com sucesso: {card_token} | Empresa: {empresa_id} | Cliente: {customer_external_id or 'N/A'}")
        
        return TokenizedCardResponse(
            card_token=card_token,
            customer_internal_id=cliente_uuid,
            customer_external_id=customer_external_id,
            customer_created=customer_created,
            expires_at=expires_at,
            encryption_method="company_key_v1",
            is_internal_token=True
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
    Agora retorna dados seguros sem descriptografar informações sensíveis.
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
        
        # 🆕 NOVO: Extrair dados seguros do JSON
        safe_card_data = card.get("safe_card_data")
        if isinstance(safe_card_data, str):
            try:
                safe_card_data = json.loads(safe_card_data)
            except json.JSONDecodeError:
                safe_card_data = {}
        elif not isinstance(safe_card_data, dict):
            safe_card_data = {}
        
        # Remove dados sensíveis da resposta - apenas dados seguros
        safe_card = {
            "card_token": card["card_token"],
            "customer_internal_id": card.get("cliente_id"),
            "customer_external_id": card.get("customer_id"),  # Para compatibilidade
            "last_four_digits": card.get("last_four_digits") or safe_card_data.get("last_four_digits"),
            "card_brand": card.get("card_brand") or safe_card_data.get("card_brand"),
            "cardholder_name": safe_card_data.get("cardholder_name"),
            "expiration_month": safe_card_data.get("expiration_month"),
            "expiration_year": safe_card_data.get("expiration_year"),
            "created_at": card.get("created_at"),
            "expires_at": card.get("expires_at"),
            "encryption_method": safe_card_data.get("tokenization_method", "company_encryption_v1"),
            "is_internal_token": True,
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


# 🆕 NOVO: Endpoint para testar resolução de token interno
@router.post("/tokenize-card/{card_token}/resolve")
async def resolve_internal_token_route(
    card_token: str,
    empresa: dict = Depends(validate_access_token)
):
    """
    🆕 NOVO: Testa a resolução de token interno para dados reais.
    
    ⚠️ ATENÇÃO: Este endpoint retorna dados sensíveis do cartão!
    Deve ser usado apenas para testes e debugging.
    Em produção, a resolução é feita automaticamente pelos gateways.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        # Usar serviço de criptografia para resolver token
        encryption_service = CompanyEncryptionService()
        
        # Verificar se é token interno
        if not encryption_service.is_internal_token(card_token):
            raise HTTPException(
                status_code=400, 
                detail="Token fornecido não é um token interno válido"
            )
        
        # Resolver token para dados reais
        card_data = await encryption_service.resolve_internal_token(empresa_id, card_token)
        
        # ⚠️ Log de segurança
        logger.warning(f"🔓 DADOS SENSÍVEIS ACESSADOS: Token {card_token} resolvido para empresa {empresa_id}")
        
        # Retornar dados reais (apenas para teste!)
        return {
            "card_token": card_token,
            "resolved_data": {
                "card_number": card_data.get("card_number", "****"),
                "expiration_month": card_data.get("expiration_month"),
                "expiration_year": card_data.get("expiration_year"),
                "security_code": card_data.get("security_code", "***"),
                "cardholder_name": card_data.get("cardholder_name")
            },
            "warning": "Dados sensíveis retornados! Use apenas para testes.",
            "encryption_method": "company_key_v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao resolver token {card_token}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao resolver token.")


# ========== ENDPOINTS DE ESTATÍSTICAS ==========

@router.get("/stats")
async def get_tokenization_stats(
    empresa: dict = Depends(validate_access_token)
):
    """
    Retorna estatísticas de tokenização da empresa.
    🔧 ATUALIZADO: Inclui informações sobre métodos de criptografia.
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
        
        # 🆕 NOVO: Estatísticas de criptografia
        encryption_stats = {"rsa_tokens": 0, "company_tokens": 0, "migrated_tokens": 0}
        
        encryption_response = (
            supabase.table("cartoes_tokenizados")
            .select("safe_card_data, encrypted_card_data")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        
        for card in (encryption_response.data or []):
            safe_data = card.get("safe_card_data")
            if safe_data:
                try:
                    if isinstance(safe_data, str):
                        safe_data = json.loads(safe_data)
                    
                    method = safe_data.get("tokenization_method", "")
                    if "company_encryption" in method:
                        encryption_stats["company_tokens"] += 1
                    elif "migrated" in method:
                        encryption_stats["migrated_tokens"] += 1
                except:
                    pass
            elif card.get("encrypted_card_data"):
                encryption_stats["rsa_tokens"] += 1
        
        # Status da criptografia da empresa
        encryption_service = CompanyEncryptionService()
        encryption_health = await encryption_service.verify_company_encryption_health(empresa_id)
        
        return {
            "total_cards": total_cards,
            "cards_by_brand": brands_count,
            "most_used_brand": max(brands_count.items(), key=lambda x: x[1])[0] if brands_count else None,
            "cards_with_customer": cards_with_customer,
            "cards_without_customer": cards_without_customer,
            "customer_linkage_rate": round((cards_with_customer / total_cards * 100), 1) if total_cards > 0 else 0,
            # 🆕 NOVO: Estatísticas de criptografia
            "encryption_stats": encryption_stats,
            "encryption_health": {
                "status": encryption_health.get("status"),
                "key_configured": encryption_health.get("key_configured"),
                "key_valid": encryption_health.get("key_valid"),
                "issues": encryption_health.get("issues", [])
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter estatísticas de tokenização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao obter estatísticas.")


# 🆕 NOVO: Endpoint para migrar tokens específicos
@router.post("/migrate-rsa-tokens")
async def migrate_rsa_tokens_route(
    empresa: dict = Depends(validate_access_token)
):
    """
    🆕 NOVO: Migra tokens RSA desta empresa para o novo sistema de criptografia.
    """
    empresa_id = empresa["empresa_id"]
    
    try:
        encryption_service = CompanyEncryptionService()
        migration_stats = await encryption_service.migrate_rsa_tokens_to_company_encryption(empresa_id)
        
        return {
            "empresa_id": empresa_id,
            "migration_completed": True,
            "stats": migration_stats,
            "message": f"Migração concluída para empresa {empresa_id}"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro na migração de tokens: {e}")
        raise HTTPException(status_code=500, detail="Erro interno na migração.")


# ========== FUNÇÕES AUXILIARES ==========

def detect_card_brand(card_number: str) -> str:
    """Detecta bandeira do cartão baseado no número."""
    # Remove espaços e hífens
    clean_number = re.sub(r'[\s-]', '', card_number)
    
    # Regras de detecção das bandeiras
    if clean_number.startswith('4'):
        return 'VISA'
    elif clean_number.startswith(('5', '2')):
        return 'MASTERCARD'
    elif clean_number.startswith(('34', '37')):
        return 'AMEX'
    elif clean_number.startswith('6'):
        return 'DISCOVER'
    elif clean_number.startswith(('38', '60')):
        return 'HIPERCARD'
    elif clean_number.startswith(('4011', '4312', '4389', '4514', '4573')):
        return 'ELO'
    else:
        return 'UNKNOWN'