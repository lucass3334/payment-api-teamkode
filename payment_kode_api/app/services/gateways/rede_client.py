import uuid
import httpx
from base64 import b64encode
from typing import Any, Dict, Optional
from fastapi import HTTPException

from payment_kode_api.app.core.config import settings
from payment_kode_api.app.services.gateways.payment_payload_mapper import map_to_rede_payload
from payment_kode_api.app.utilities.logging_config import logger

# ✅ MANTÉM: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    ConfigRepositoryInterface,
    PaymentRepositoryInterface,
)

# 🆕 NOVO: Import do serviço de criptografia por empresa
from ...services.company_encryption import CompanyEncryptionService

TIMEOUT = 15.0

# ─── URLs CORRIGIDAS CONFORME MANUAL OFICIAL ────────────────────────────────────────────────
# 🔧 CORRIGIDO: URLs corretas da e.Rede conforme documentação oficial (página 8 do manual)
rede_env = getattr(settings, 'REDE_AMBIENT', 'production')
if rede_env.lower() == "sandbox":
    # ✅ URL CORRETA: Sandbox conforme manual
    # Sandbox: https://sandbox-erede.useredecloud.com.br/v1/transactions
    BASE_URL = "https://sandbox-erede.useredecloud.com.br"
    API_VERSION = "v1"
else:
    # ✅ URL CORRETA: Produção conforme manual  
    # Production: https://api.userede.com.br/erede/v1/transactions
    BASE_URL = "https://api.userede.com.br"
    API_VERSION = "erede/v1"

# Montar URLs finais
TRANSACTIONS_URL = f"{BASE_URL}/{API_VERSION}/transactions"
CARD_URL = f"{BASE_URL}/{API_VERSION}/card"  # Para tokenização

# 🔧 NOVO: Log das URLs para debugging
logger.info(f"🔧 Rede configurada - Ambiente: {rede_env}")
logger.info(f"📍 Base URL: {BASE_URL}")
logger.info(f"📍 API Version: {API_VERSION}")
logger.info(f"📍 Transações: {TRANSACTIONS_URL}")
logger.info(f"📍 Cartões: {CARD_URL}")


# 🆕 NOVAS FUNÇÕES: Resolução de Token Interno

async def resolve_internal_token(empresa_id: str, card_token: str) -> Dict[str, Any]:
    """
    🆕 NOVA FUNÇÃO: Resolve token interno para dados reais do cartão.
    
    Args:
        empresa_id: ID da empresa
        card_token: Token interno do cartão (UUID)
        
    Returns:
        Dados reais do cartão para usar com a Rede
        
    Raises:
        ValueError: Se token não encontrado ou inválido
        Exception: Se erro na descriptografia
    """
    try:
        # 1. Buscar token no banco
        from ...database.database import get_tokenized_card
        card = await get_tokenized_card(card_token)
        
        if not card or card["empresa_id"] != empresa_id:
            raise ValueError("Token não encontrado ou não pertence à empresa")
        
        # 2. Buscar chave da empresa e descriptografar
        encryption_service = CompanyEncryptionService()
        decryption_key = await encryption_service.get_empresa_decryption_key(empresa_id)
        
        # 3. Descriptografar dados
        encrypted_data = card.get("encrypted_card_data")
        if not encrypted_data:
            raise ValueError("Dados criptografados não encontrados para o token")
        
        card_data = encryption_service.decrypt_card_data_with_company_key(
            encrypted_data, 
            decryption_key
        )
        
        logger.info(f"✅ Token interno resolvido para dados reais: {card_token[:8]}...")
        return card_data
        
    except Exception as e:
        logger.error(f"❌ Erro ao resolver token interno {card_token}: {e}")
        raise


def is_internal_token(token: str) -> bool:
    """
    🆕 NOVA FUNÇÃO: Verifica se um token é interno (UUID) ou externo da Rede.
    
    Args:
        token: Token a ser verificado
        
    Returns:
        True se for token interno (UUID format)
    """
    try:
        uuid.UUID(token)
        return True
    except (ValueError, TypeError):
        return False


async def debug_card_data_structure(empresa_id: str, card_token: str) -> Dict[str, Any]:
    """
    🧪 FUNÇÃO DE DEBUG: Analisa estrutura dos dados do cartão descriptografados.
    Útil para identificar problemas com nomes de campos.
    """
    try:
        real_card_data = await resolve_internal_token(empresa_id, card_token)
        
        debug_info = {
            "available_fields": list(real_card_data.keys()),
            "field_values": {k: "***" if k in ["card_number", "security_code"] else v 
                           for k, v in real_card_data.items()},
            "has_required_fields": {
                "card_number": any(k in real_card_data for k in ["card_number", "number", "cardNumber"]),
                "expiration_month": any(k in real_card_data for k in ["expiration_month", "expirationMonth", "month"]),
                "expiration_year": any(k in real_card_data for k in ["expiration_year", "expirationYear", "year"]),
                "security_code": any(k in real_card_data for k in ["security_code", "securityCode", "cvv", "ccv"]),
                "cardholder_name": any(k in real_card_data for k in ["cardholder_name", "holderName", "name"])
            }
        }
        
        logger.info(f"🔍 Debug card data: {debug_info}")
        return debug_info
        
    except Exception as e:
        logger.error(f"❌ Erro no debug: {e}")
        return {"error": str(e)}


# ✅ MANTÉM: Funções existentes com pequenas melhorias

async def get_rede_headers(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, str]:
    """
    ✅ MIGRADO: Retorna headers com Basic Auth (PV + Integration Key).
    🔧 MELHORADO: Headers mais completos e logs de debugging.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # ✅ USANDO INTERFACE
    config = await config_repo.get_empresa_config(empresa_id)
    if not config:
        raise HTTPException(
            status_code=401,
            detail=f"Configuração da empresa {empresa_id} não encontrada"
        )

    pv = config.get("rede_pv")
    api_key = config.get("rede_api_key")
    if not pv or not api_key:
        raise HTTPException(
            status_code=401,
            detail=f"Credenciais da Rede não encontradas para empresa {empresa_id}"
        )

    auth = b64encode(f"{pv}:{api_key}".encode()).decode()
    
    # 🔧 MELHORADO: Headers mais completos conforme documentação da Rede
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PaymentKode-API/1.0"
    }
    
    logger.debug(f"🔐 Headers Rede preparados para empresa {empresa_id}")
    return headers


async def create_rede_payment(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None,
    payment_repo: Optional[PaymentRepositoryInterface] = None,
    **payment_data: Any
) -> Dict[str, Any]:
    """
    🔧 ATUALIZADO: Autoriza (e captura, se capture=True) uma transação.
    🆕 NOVO: Agora detecta e resolve tokens internos automaticamente.
    🔧 CORRIGIDO: Estrutura correta do payload para evitar erro ExpirationMonth.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    if payment_repo is None:
        from ...dependencies import get_payment_repository
        payment_repo = get_payment_repository()

    # 🆕 NOVO: Resolução automática de token interno
    resolved_card_data = None
    if payment_data.get("card_token"):
        card_token = payment_data["card_token"]
        
        # Verificar se é token interno (UUID)
        if is_internal_token(card_token):
            logger.info(f"🔄 Detectado token interno, resolvendo: {card_token[:8]}...")
            
            try:
                # Resolver para dados reais
                real_card_data = await resolve_internal_token(empresa_id, card_token)
                resolved_card_data = real_card_data
                logger.info("✅ Token interno resolvido - usando dados reais para Rede")
                
                # 🧪 DEBUG: Analisar estrutura dos dados (remover em produção)
                await debug_card_data_structure(empresa_id, card_token)
                
            except Exception as e:
                logger.error(f"❌ Erro ao resolver token interno: {e}")
                raise HTTPException(status_code=400, detail=f"Erro ao resolver token: {str(e)}")
        else:
            logger.info(f"🏷️ Token externo da Rede detectado: {card_token[:8]}...")
    
    # 🔧 CORRIGIDO: Preparar payload com estrutura correta
    try:
        # Garantir que amount seja numérico
        amount_value = float(payment_data["amount"]) if not isinstance(payment_data["amount"], (int, float)) else payment_data["amount"]
        
        # Estrutura base do payload
        payload: Dict[str, Any] = {
            "capture": payment_data.get("capture", True),
            "kind": payment_data.get("kind", "credit"),
            "reference": payment_data.get("transaction_id", ""),
            "amount": int(amount_value * 100),  # Converter para centavos
            "installments": payment_data.get("installments", 1),
            "softDescriptor": payment_data.get("soft_descriptor", "PAYMENT_KODE")
        }
        
        # ========== 🔧 CORRIGIDO: Preparação robusta dos dados do cartão ==========
        if resolved_card_data:
            # ✅ DEBUGGING: Log dos dados resolvidos para identificar problema
            logger.debug(f"🔍 Dados resolvidos do token: {list(resolved_card_data.keys())}")
            
            # ✅ NORMALIZAÇÃO: Mapear todos os possíveis nomes de campos
            card_number = (
                resolved_card_data.get("card_number") or 
                resolved_card_data.get("number") or 
                resolved_card_data.get("cardNumber")
            )
            
            expiration_month = (
                resolved_card_data.get("expiration_month") or 
                resolved_card_data.get("expirationMonth") or 
                resolved_card_data.get("month")
            )
            
            expiration_year = (
                resolved_card_data.get("expiration_year") or 
                resolved_card_data.get("expirationYear") or 
                resolved_card_data.get("year")
            )
            
            security_code = (
                resolved_card_data.get("security_code") or 
                resolved_card_data.get("securityCode") or 
                resolved_card_data.get("cvv") or 
                resolved_card_data.get("ccv")
            )
            
            cardholder_name = (
                resolved_card_data.get("cardholder_name") or 
                resolved_card_data.get("holderName") or 
                resolved_card_data.get("name")
            )
            
            # ✅ VALIDAÇÃO: Verificar se todos os campos necessários estão presentes
            missing_fields = []
            if not card_number:
                missing_fields.append("card_number")
            if not expiration_month:
                missing_fields.append("expiration_month")
            if not expiration_year:
                missing_fields.append("expiration_year")
            if not security_code:
                missing_fields.append("security_code")
            if not cardholder_name:
                missing_fields.append("cardholder_name")
            
            if missing_fields:
                logger.error(f"❌ Campos obrigatórios ausentes nos dados do token: {missing_fields}")
                logger.error(f"❌ Dados disponíveis: {list(resolved_card_data.keys())}")
                raise ValueError(f"Dados do cartão incompletos: {missing_fields}")
            
            # ✅ CORRIGIDO: Estrutura final com validação de formato
            try:
                month_int = int(expiration_month)
                if month_int < 1 or month_int > 12:
                    raise ValueError(f"Mês inválido: {month_int}")
                
                year_str = str(expiration_year)
                if len(year_str) == 2:
                    # Converter YY para YYYY
                    year_int = int(year_str)
                    # 🔧 CORRIGIDO: Lógica atualizada para 2025+
                    # Cartões tipicamente expiram 3-5 anos no futuro
                    # Anos 00-49 = 20XX, anos 50-99 = 19XX (para compatibilidade com cartões muito antigos)
                    if year_int <= 49:  # 00-49 = 20XX
                        year_str = f"20{year_str}"
                    else:  # 50-99 = 19XX (casos muito raros)
                        year_str = f"19{year_str}"
                
                # 🔧 NOVO: Validação adicional para anos no passado
                from datetime import datetime
                current_year = datetime.now().year
                year_final = int(year_str)
                
                if year_final < current_year:
                    logger.warning(f"⚠️ Ano do cartão parece estar no passado: {year_final}. Ano atual: {current_year}")
                    # Não bloquear, apenas alertar, pois pode ser intencional para testes
                elif year_final > current_year + 10:
                    logger.warning(f"⚠️ Ano do cartão parece muito distante: {year_final}. Ano atual: {current_year}")
                
                # 🔧 NOVO: Validação de mês/ano combinados para cartões expirados
                if year_final == current_year:
                    from datetime import datetime
                    current_month = datetime.now().month
                    if month_int < current_month:
                        logger.warning(f"⚠️ Cartão pode estar expirado: {month_int:02d}/{year_final}")
                        # Não bloquear em sandbox, apenas alertar
                
                # 🔧 CORREÇÃO FINAL: API da Rede espera NÚMEROS INTEIROS, não strings!
                # Baseado na documentação oficial da e.Rede (páginas 9-11)
                try:
                    month_int = int(month_int)  # Garantir que é inteiro
                    year_int = int(year_str)    # Garantir que é inteiro
                    
                    # ✅ ESTRUTURA CORRETA conforme documentação oficial da e.Rede
                    payload["card"] = {
                        "number": str(card_number),
                        "expirationMonth": month_int,    # NÚMERO INTEIRO conforme doc
                        "expirationYear": year_int,      # NÚMERO INTEIRO conforme doc  
                        "securityCode": str(security_code),
                        "holderName": str(cardholder_name)
                    }
                    
                    logger.info(f"✅ Payload do cartão preparado (formato correto): number=***{str(card_number)[-4:]}, expirationMonth={month_int}, expirationYear={year_int}")
                    
                except (ValueError, TypeError) as e:
                    logger.error(f"❌ Erro ao converter dados para números inteiros: {e}")
                    raise ValueError(f"Dados do cartão com formato inválido: {str(e)}")
                
                logger.debug(f"🔍 Estrutura completa do payload card: {payload['card']}")
                
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Erro ao formatar dados do cartão: {e}")
                raise ValueError(f"Dados do cartão inválidos: {str(e)}")
                
        elif payment_data.get("card_token") and not is_internal_token(payment_data["card_token"]):
            # Token externo da Rede
            payload["cardToken"] = payment_data["card_token"]
            logger.info(f"✅ Usando token externo da Rede: {payment_data['card_token'][:8]}...")
            
        elif payment_data.get("card_data"):
            # Dados diretos do cartão
            card_data = payment_data["card_data"]
            
            try:
                month_int = int(card_data["expiration_month"])
                year_int = int(card_data["expiration_year"])
                
                # 🔧 CORREÇÃO FINAL: Dados diretos também devem ser números inteiros
                payload["card"] = {
                    "number": str(card_data["card_number"]),
                    "expirationMonth": month_int,     # NÚMERO INTEIRO
                    "expirationYear": year_int,       # NÚMERO INTEIRO
                    "securityCode": str(card_data["security_code"]),
                    "holderName": str(card_data["cardholder_name"])
                }
                
                logger.info(f"✅ Usando dados diretos do cartão (formato correto): ***{str(card_data['card_number'])[-4:]}, expirationMonth={month_int}, expirationYear={year_int}")
                
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"❌ Erro nos dados diretos do cartão: {e}")
                raise ValueError(f"Dados do cartão inválidos: {str(e)}")
                
        else:
            raise ValueError("É necessário fornecer card_token ou card_data")
        
        logger.debug(f"✅ Payload preparado corretamente: {payload}")
        
        # 🔧 NOVO: Log especial para debugging ExpirationMonth
        if "card" in payload:
            card_payload = payload["card"]
            logger.info(f"🔍 DEBUGGING EXPIRATION: expirationMonth='{card_payload.get('expirationMonth')}', expirationYear='{card_payload.get('expirationYear')}'")
            
            # Verificar se algum campo está None ou vazio
            for field_name, field_value in card_payload.items():
                if field_value is None or field_value == "":
                    logger.error(f"❌ Campo do cartão está vazio: {field_name} = '{field_value}'")
        
    except Exception as e:
        logger.error(f"❌ Erro ao preparar payload: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao preparar dados do pagamento: {str(e)}")

    headers = await get_rede_headers(empresa_id, config_repo)
    
    # 🔧 NOVO: Validação final antes do envio
    if "card" in payload:
        required_card_fields = ["number", "expirationMonth", "expirationYear", "securityCode", "holderName"]
        card_data = payload["card"]
        
        for field in required_card_fields:
            if field not in card_data or not card_data[field] or card_data[field] == "":
                logger.error(f"❌ VALIDATION FAILED: Campo obrigatório ausente ou vazio: {field}")
                logger.error(f"❌ Card payload atual: {card_data}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Campo obrigatório do cartão está ausente ou vazio: {field}"
                )
        
        logger.info(f"✅ Validação de campos obrigatórios passou")
    
    # 🔧 NOVO: Logs detalhados para debugging
    logger.info(f"🚀 Enviando pagamento à Rede: empresa={empresa_id}")
    logger.info(f"📍 URL: {TRANSACTIONS_URL}")
    logger.info(f"🔧 Ambiente: {rede_env}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TRANSACTIONS_URL, json=payload, headers=headers)
            
            # 🔧 NOVO: Log detalhado da resposta para debugging
            logger.info(f"📥 Rede Response Status: {resp.status_code}")
            
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: RESPONSE HANDLING MELHORADO
            return_code = data.get("returnCode", "")
            return_message = data.get("returnMessage", "")
            tid = data.get("tid")
            authorization_code = data.get("authorizationCode")
            
            logger.info(f"📥 Rede response: code={return_code}, message={return_message}, tid={tid}")
            
            # 🔧 NOVO: Atualizar pagamento no banco com dados da Rede - ✅ USANDO INTERFACE
            transaction_id = payment_data.get("transaction_id")
            if transaction_id and return_code == "00":
                # Salvar dados da Rede no banco
                await payment_repo.update_payment_status(
                    transaction_id=transaction_id,
                    empresa_id=empresa_id,
                    status="approved",
                    extra_data={
                        "rede_tid": tid,
                        "authorization_code": authorization_code,
                        "return_code": return_code,
                        "return_message": return_message
                    }
                )
                logger.info(f"✅ Status do pagamento atualizado no banco: {transaction_id}")
            
            # Retorno estruturado
            if return_code == "00":  # Sucesso
                return {
                    "status": "approved",
                    "transaction_id": transaction_id,
                    "rede_tid": tid,
                    "authorization_code": authorization_code,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }
            else:
                # Pagamento recusado
                logger.warning(f"⚠️ Pagamento Rede recusado: {return_code} - {return_message}")
                return {
                    "status": "failed",
                    "transaction_id": transaction_id,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }

    except httpx.HTTPStatusError as e:
        code, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede retornou HTTP {code}: {text}")
        
        # 🔧 MELHORADO: Tratamento específico para erros comuns
        if code == 404:
            logger.error(f"❌ ERRO 404: Endpoint não encontrado!")
            logger.error(f"❌ URL usada: {TRANSACTIONS_URL}")
            raise HTTPException(
                status_code=502, 
                detail=f"Endpoint da Rede não encontrado (404). Ambiente: {rede_env} | URL: {TRANSACTIONS_URL}"
            )
        elif code == 405:
            logger.error(f"❌ ERRO 405: Método não permitido! URL: {TRANSACTIONS_URL}")
            raise HTTPException(
                status_code=502, 
                detail=f"Método não permitido pela Rede (405). Ambiente: {rede_env}"
            )
        
        if code in (400, 402, 403):
            raise HTTPException(status_code=code, detail=f"Pagamento recusado pela Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão com a Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar pagamento na Rede")


async def tokenize_rede_card(
    empresa_id: str, 
    card_data: Dict[str, Any],
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> str:
    """
    ✅ MIGRADO: Tokeniza o cartão na Rede.
    🔧 CORRIGIDO: Usando URL correta e logs melhorados.
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    payload = {
        "number":          card_data["card_number"],
        "expirationMonth": int(card_data["expiration_month"]),  # Garantir formato 01, 02, etc.
        "expirationYear":  int(card_data["expiration_year"]),
        "securityCode":    card_data["security_code"],
        "holderName":      card_data["cardholder_name"],
    }
    
    logger.info(f"🔐 Tokenizando cartão na Rede: {CARD_URL}")
    logger.debug(f"📦 Payload tokenização: {payload}")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(CARD_URL, json=payload, headers=headers)
            
            # 🔧 NOVO: Log da resposta para debugging
            logger.info(f"📥 Tokenização Rede Status: {resp.status_code}")
            
            resp.raise_for_status()
            result = resp.json()
            token = result.get("cardToken")
            
            if token:
                logger.info(f"✅ Cartão tokenizado com sucesso na Rede")
                return token
            else:
                logger.error(f"❌ Token não retornado pela Rede: {result}")
                raise HTTPException(status_code=502, detail="Token não retornado pela Rede")
                
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Rede tokenização HTTP {e.response.status_code}: {e.response.text}")
        
        # 🔧 MELHORADO: Tratamento específico para erros comuns
        if e.response.status_code == 404:
            logger.error(f"❌ ERRO 404 na tokenização: Endpoint não encontrado! URL: {CARD_URL}")
            raise HTTPException(
                status_code=502, 
                detail=f"Endpoint da Rede não encontrado (404). Ambiente: {rede_env} | URL: {CARD_URL}"
            )
        elif e.response.status_code == 405:
            logger.error(f"❌ ERRO 405 na tokenização: Método não permitido! URL: {CARD_URL}")
            raise HTTPException(
                status_code=502, 
                detail=f"Método não permitido pela Rede (405). Ambiente: {rede_env}"
            )
        
        raise HTTPException(status_code=502, detail="Erro ao tokenizar cartão na Rede")
    except Exception as e:
        logger.error(f"❌ Rede tokenização erro: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao tokenizar cartão na Rede")


async def capture_rede_transaction(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Confirma (captura) uma autorização prévia.
    Endpoint: PUT /v1/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    logger.info(f"🔄 Capturando transação Rede: {url}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.put(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede capture HTTP {status}: {text}")
        if status in (400, 403, 404):
            raise HTTPException(
                status_code=status,
                detail=f"Erro ao capturar transação Rede: {text}"
            )
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao capturar transação")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao capturar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao capturar transação na Rede")


async def get_rede_transaction(
    empresa_id: str,
    transaction_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Consulta o status de uma transação.
    Endpoint: GET /v1/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"

    logger.info(f"🔍 Consultando transação Rede: {url}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede consulta HTTP {status}: {text}")
        raise HTTPException(status_code=status, detail="Erro ao buscar transação na Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao consultar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao consultar transação na Rede")


async def create_rede_refund(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None,
    config_repo: Optional[ConfigRepositoryInterface] = None,
    payment_repo: Optional[PaymentRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Solicita estorno usando TID da Rede (não nosso transaction_id).
    Endpoint: POST /v1/transactions/{rede_tid}/refunds
    """
    # ✅ LAZY LOADING: Dependency injection
    if payment_repo is None:
        from ...dependencies import get_payment_repository
        payment_repo = get_payment_repository()
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # 🔧 NOVO: Buscar TID da Rede no banco - ✅ USANDO INTERFACE
    payment = await payment_repo.get_payment(transaction_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")
    
    rede_tid = payment.get("rede_tid")
    if not rede_tid:
        raise HTTPException(400, "TID da Rede não encontrado para este pagamento")
    
    headers = await get_rede_headers(empresa_id, config_repo)
    # 🔧 CORRIGIDO: Usar rede_tid ao invés de transaction_id
    url = f"{TRANSACTIONS_URL}/{rede_tid}/refunds"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    try:
        logger.info(f"🔄 Solicitando estorno Rede: POST {url} – payload={payload}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: Verificar código de retorno do estorno
            return_code = data.get("returnCode", "")
            if return_code == "00":
                # Atualizar status no banco - ✅ USANDO INTERFACE
                await payment_repo.update_payment_status(transaction_id, empresa_id, "canceled")
                logger.info(f"✅ Estorno Rede processado com sucesso: {transaction_id}")
                return {"status": "refunded", **data}
            else:
                logger.warning(f"⚠️ Estorno Rede falhou: {return_code} - {data.get('returnMessage')}")
                raise HTTPException(400, f"Estorno Rede falhou: {data.get('returnMessage')}")

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede estorno HTTP {status}: {text}")
        if status in (400, 402, 403, 404):
            raise HTTPException(status_code=status, detail=f"Erro no estorno Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao processar estorno")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao estornar na Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar estorno na Rede")


# 🆕 NOVA: Função para testar conectividade com a Rede
async def test_rede_connectivity(empresa_id: str) -> Dict[str, Any]:
    """
    🧪 NOVO: Testa a conectividade com a API da Rede.
    Útil para debugging de problemas de endpoint.
    """
    try:
        headers = await get_rede_headers(empresa_id)
        
        # Teste simples fazendo uma requisição GET mínima
        test_endpoints = [
            {
                "url": f"{BASE_URL}/{API_VERSION}", 
                "method": "GET", 
                "description": "Base API URL"
            },
            {
                "url": TRANSACTIONS_URL, 
                "method": "GET", 
                "description": "Transactions endpoint"
            },
        ]
        
        results = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in test_endpoints:
                try:
                    if endpoint["method"] == "GET":
                        resp = await client.get(endpoint["url"], headers=headers)
                    else:
                        resp = await client.post(endpoint["url"], headers=headers, json={})
                    
                    results.append({
                        "endpoint": endpoint["description"],
                        "url": endpoint["url"],
                        "status_code": resp.status_code,
                        "status": "success" if resp.status_code < 500 else "warning",
                        "response_size": len(resp.content) if resp.content else 0
                    })
                    
                except Exception as e:
                    results.append({
                        "endpoint": endpoint["description"],
                        "url": endpoint["url"],
                        "status": "error",
                        "error": str(e)
                    })
        
        return {
            "status": "completed",
            "environment": rede_env,
            "base_url": BASE_URL,
            "api_version": API_VERSION,
            "transactions_url": TRANSACTIONS_URL,
            "card_url": CARD_URL,
            "empresa_id": empresa_id,
            "tests": results,
            "message": f"Teste de conectividade concluído para ambiente {rede_env}"
        }
            
    except Exception as e:
        return {
            "status": "error",
            "environment": rede_env,
            "base_url": BASE_URL,
            "api_version": API_VERSION,
            "transactions_url": TRANSACTIONS_URL,
            "empresa_id": empresa_id,
            "error": str(e),
            "message": "Falha crítica no teste de conectividade"
        }


# ========== CLASSE WRAPPER PARA INTERFACE ==========

class RedeGateway:
    """
    ✅ MANTÉM: Classe wrapper que implementa RedeGatewayInterface
    🆕 NOVO: Agora com suporte a resolução de tokens internos
    """
    
    def __init__(
        self,
        config_repo: Optional[ConfigRepositoryInterface] = None,
        payment_repo: Optional[PaymentRepositoryInterface] = None
    ):
        # ✅ LAZY LOADING nos constructors também
        if config_repo is None:
            from ...dependencies import get_config_repository
            config_repo = get_config_repository()
        if payment_repo is None:
            from ...dependencies import get_payment_repository
            payment_repo = get_payment_repository()
            
        self.config_repo = config_repo
        self.payment_repo = payment_repo
    
    async def create_payment(self, empresa_id: str, **kwargs) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.create_payment"""
        return await create_rede_payment(
            empresa_id,
            config_repo=self.config_repo,
            payment_repo=self.payment_repo,
            **kwargs
        )
    
    async def create_refund(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.create_refund"""
        return await create_rede_refund(
            empresa_id,
            transaction_id,
            amount,
            config_repo=self.config_repo,
            payment_repo=self.payment_repo
        )
    
    async def tokenize_card(self, empresa_id: str, card_data: Dict[str, Any]) -> str:
        """Implementa RedeGatewayInterface.tokenize_card"""
        return await tokenize_rede_card(
            empresa_id,
            card_data,
            config_repo=self.config_repo
        )
    
    async def capture_transaction(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.capture_transaction"""
        return await capture_rede_transaction(
            empresa_id,
            transaction_id,
            amount,
            config_repo=self.config_repo
        )
    
    async def get_transaction(self, empresa_id: str, transaction_id: str) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.get_transaction"""
        return await get_rede_transaction(
            empresa_id,
            transaction_id,
            config_repo=self.config_repo
        )
    
    async def test_connectivity(self, empresa_id: str) -> Dict[str, Any]:
        """🆕 NOVO: Testa conectividade"""
        return await test_rede_connectivity(empresa_id)


# ========== FUNÇÃO PARA DEPENDENCY INJECTION ==========

def get_rede_gateway_instance() -> RedeGateway:
    """
    ✅ MANTÉM: Função para criar instância do RedeGateway
    Pode ser usada nos dependencies.py
    """
    return RedeGateway()


# ========== BACKWARD COMPATIBILITY ==========
# Mantém as funções originais para compatibilidade, mas agora elas usam interfaces

async def create_rede_payment_legacy(empresa_id: str, **payment_data: Any) -> Dict[str, Any]:
    """
    ⚠️ DEPRECATED: Use create_rede_payment com dependency injection
    Mantido apenas para compatibilidade
    """
    logger.warning("⚠️ Usando função legacy create_rede_payment_legacy. Migre para a nova versão com interfaces.")
    return await create_rede_payment(empresa_id, **payment_data)


# ========== EXPORTS ==========

__all__ = [
    "resolve_internal_token",
    "is_internal_token",
    "debug_card_data_structure",
    "get_rede_headers",
    "tokenize_rede_card",
    "create_rede_payment",
    "capture_rede_transaction",
    "get_rede_transaction",
    "create_rede_refund",
    "test_rede_connectivity",
    "RedeGateway",
    "get_rede_gateway_instance",
    "create_rede_payment_legacy",
]