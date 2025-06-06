# payment_kode_api/app/security/crypto.py

import hashlib
import json
import base64
from typing import Dict, Any
from ..database import get_empresa_certificados
from ..utilities.logging_config import logger

# ========== FUNÇÕES ANTIGAS (DEPRECATED MAS FUNCIONAIS) ==========

async def encrypt_card_data(empresa_id: str, card_data: dict) -> str:
    """
    ⚠️ DEPRECATED: Função antiga com RSA, agora com fallback inteligente.
    
    Comportamento:
    1. Tenta usar RSA se chaves estiverem disponíveis
    2. Se falhar, usa método simples como fallback
    3. Mantém compatibilidade com código existente
    
    Use CardTokenizationService para novos casos.
    """
    logger.info(f"🔐 Tentando criptografar cartão para empresa {empresa_id}")
    
    try:
        # Tentar abordagem antiga (RSA)
        return await _encrypt_card_data_rsa(empresa_id, card_data)
    except Exception as rsa_error:
        logger.warning(f"⚠️ RSA falhou para empresa {empresa_id}: {rsa_error}")
        logger.info("🔄 Usando fallback com método simples...")
        
        # Fallback para método simples
        return await _encrypt_card_data_simple(empresa_id, card_data)


async def decrypt_card_data(empresa_id: str, encrypted_data: str) -> dict:
    """
    ⚠️ DEPRECATED: Para compatibilidade com código existente.
    
    Comportamento:
    1. Detecta o método usado (RSA ou simples)
    2. Descriptografa/decodifica accordingly
    3. Retorna dados disponíveis (pode não incluir número/CVV)
    """
    logger.info(f"🔓 Tentando descriptografar para empresa {empresa_id}")
    
    try:
        # Tentar detectar formato
        data = json.loads(encrypted_data)
        
        if data.get("method") == "simple_hash":
            # Novo método - retorna dados seguros apenas
            logger.info("📄 Detectado método simples, retornando dados seguros")
            return {
                "cardholder_name": data.get("cardholder_name", ""),
                "expiration_month": data.get("expiration_month", ""),
                "expiration_year": data.get("expiration_year", ""),
                "last_four_digits": data.get("last_four_digits", ""),
                "card_brand": data.get("card_brand", "UNKNOWN"),
                "_method": "simple_hash",
                "_note": "Dados sensíveis não disponíveis por segurança"
            }
        else:
            # Pode ser RSA ou outro formato
            logger.info("🔐 Detectado possível formato RSA")
            return await _decrypt_card_data_rsa(empresa_id, encrypted_data)
            
    except json.JSONDecodeError:
        # Provavelmente é RSA (Base64)
        logger.info("🔐 Formato não-JSON detectado, tentando RSA")
        return await _decrypt_card_data_rsa(empresa_id, encrypted_data)
    except Exception as e:
        logger.error(f"❌ Erro ao descriptografar: {e}")
        raise ValueError(f"Dados do cartão ilegíveis: {str(e)}")


# ========== IMPLEMENTAÇÕES INTERNAS ==========

async def _encrypt_card_data_rsa(empresa_id: str, card_data: dict) -> str:
    """Método antigo com RSA - pode falhar se chaves não existirem."""
    try:
        # Suas funções RSA originais
        public_key = await get_public_key(empresa_id)
        plaintext = f"{card_data['card_number']}|{card_data['security_code']}|{card_data['expiration_month']}|{card_data['expiration_year']}"
        
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        
        ciphertext = public_key.encrypt(
            plaintext.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        encrypted_b64 = base64.b64encode(ciphertext).decode()
        logger.info(f"✅ RSA encryption bem-sucedido para empresa {empresa_id}")
        return encrypted_b64
        
    except Exception as e:
        logger.error(f"❌ RSA encryption falhou: {e}")
        raise


async def _encrypt_card_data_simple(empresa_id: str, card_data: dict) -> str:
    """Método simples de fallback usando o novo serviço."""
    try:
        from ..services.card_tokenization_service import CardTokenizationService
        
        # Usar novo serviço
        service = CardTokenizationService()
        token_data = service.create_card_token(empresa_id, card_data)
        
        # Retorna JSON dos dados seguros (compatível com decrypt)
        safe_data = {
            "method": "simple_hash",
            "cardholder_name": card_data["cardholder_name"],
            "expiration_month": card_data["expiration_month"],
            "expiration_year": card_data["expiration_year"],
            "last_four_digits": card_data["card_number"][-4:],
            "card_brand": token_data["card_brand"],
            "card_hash": token_data["card_hash"],
            "created_at": token_data["created_at"]
        }
        
        result = json.dumps(safe_data)
        logger.info(f"✅ Simple encryption bem-sucedido para empresa {empresa_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Simple encryption falhou: {e}")
        raise


async def _decrypt_card_data_rsa(empresa_id: str, encrypted_data: str) -> dict:
    """Método antigo de descriptografia RSA."""
    try:
        private_key = await get_private_key(empresa_id)
        
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        
        decrypted_bytes = private_key.decrypt(
            base64.b64decode(encrypted_data),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        decrypted_text = decrypted_bytes.decode()
        card_number, security_code, expiration_month, expiration_year = decrypted_text.split('|')
        
        result = {
            "card_number": card_number,
            "security_code": security_code,
            "expiration_month": expiration_month,
            "expiration_year": expiration_year,
            "_method": "rsa_decryption"
        }
        
        logger.info(f"✅ RSA decryption bem-sucedido para empresa {empresa_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ RSA decryption falhou: {e}")
        raise


async def get_private_key(empresa_id: str):
    """Busca a chave privada RSA da empresa no banco de dados."""
    certificados = await get_empresa_certificados(empresa_id)
    
    # ✅ CORRIGIDO: Usar campo correto do banco
    if not certificados or not certificados.get("sicredi_cert_base64"):
        raise ValueError(f"Chave privada não encontrada para empresa {empresa_id}")
    
    private_key_pem = base64.b64decode(certificados["sicredi_cert_base64"])
    
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(private_key_pem, password=None)


async def get_public_key(empresa_id: str):
    """Busca a chave pública RSA da empresa no banco de dados."""
    certificados = await get_empresa_certificados(empresa_id)
    
    # ✅ CORRIGIDO: Usar campo correto do banco  
    if not certificados or not certificados.get("sicredi_key_base64"):
        raise ValueError(f"Chave pública não encontrada para empresa {empresa_id}")
    
    public_key_pem = base64.b64decode(certificados["sicredi_key_base64"])
    
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_public_key(public_key_pem)


# ========== NOVAS FUNÇÕES (RECOMENDADAS) ==========

async def tokenize_card_secure(empresa_id: str, card_data: Dict[str, Any]) -> str:
    """
    ✅ NOVA: Função recomendada para tokenização.
    Retorna token que pode ser usado com gateways.
    """
    try:
        from ..services.card_tokenization_service import CardTokenizationService
        
        service = CardTokenizationService()
        token_data = service.create_card_token(empresa_id, card_data)
        
        logger.info(f"✅ Token seguro criado para empresa {empresa_id}")
        return token_data["card_token"]
        
    except Exception as e:
        logger.error(f"❌ Erro na tokenização segura: {e}")
        raise


async def get_card_safe_data(card_token: str, empresa_id: str) -> Dict[str, Any]:
    """
    ✅ NOVA: Recupera dados seguros do cartão (sem número/CVV).
    Para exibição ao usuário ou validações.
    """
    try:
        # Buscar no banco pelo token
        from ..database.database import get_tokenized_card
        
        card_data = await get_tokenized_card(card_token)
        
        if not card_data:
            raise ValueError("Token não encontrado")
        
        if card_data["empresa_id"] != empresa_id:
            raise ValueError("Token não pertence à empresa")
        
        # Verificar expiração
        from ..services.card_tokenization_service import CardTokenizationService
        service = CardTokenizationService()
        
        if service.is_token_expired(card_data.get("expires_at", "")):
            raise ValueError("Token expirado")
        
        # Retornar dados seguros
        safe_data = {
            "card_token": card_token,
            "last_four_digits": card_data.get("last_four_digits"),
            "card_brand": card_data.get("card_brand"),
            "cardholder_name": card_data.get("cardholder_name"),
            "expiration_month": card_data.get("expiration_month"),
            "expiration_year": card_data.get("expiration_year"),
            "created_at": card_data.get("created_at"),
            "expires_at": card_data.get("expires_at"),
            "is_expired": False
        }
        
        logger.info(f"✅ Dados seguros recuperados para token {card_token}")
        return safe_data
        
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar dados seguros do token {card_token}: {e}")
        raise


async def verify_card_with_token(card_token: str, empresa_id: str, card_number: str, security_code: str) -> bool:
    """
    ✅ NOVA: Verifica se dados do cartão batem com o token.
    Útil para validar pagamentos sem armazenar dados sensíveis.
    """
    try:
        from ..database.database import get_tokenized_card
        from ..services.card_tokenization_service import CardTokenizationService
        
        # Buscar token no banco
        card_data = await get_tokenized_card(card_token)
        
        if not card_data or card_data["empresa_id"] != empresa_id:
            return False
        
        # Extrair hash armazenado
        safe_card_data = card_data.get("safe_card_data")
        if isinstance(safe_card_data, str):
            safe_card_data = json.loads(safe_card_data)
        
        stored_hash = safe_card_data.get("card_hash")
        if not stored_hash:
            logger.warning(f"⚠️ Hash não encontrado para token {card_token}")
            return False
        
        # Verificar hash
        service = CardTokenizationService()
        is_valid = service.verify_card_hash(empresa_id, stored_hash, card_number, security_code)
        
        if is_valid:
            logger.info(f"✅ Verificação de cartão bem-sucedida para token {card_token}")
        else:
            logger.warning(f"⚠️ Verificação de cartão falhou para token {card_token}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"❌ Erro na verificação do token {card_token}: {e}")
        return False


# ========== MIGRAÇÃO HELPERS ==========

async def migrate_rsa_to_simple(empresa_id: str) -> Dict[str, Any]:
    """
    🔧 HELPER: Migra tokens RSA existentes para formato simples.
    Para executar uma vez na migração.
    """
    migration_stats = {
        "processed": 0,
        "migrated": 0,
        "errors": 0,
        "skipped": 0
    }
    
    try:
        from ..database.database import supabase
        
        # Buscar tokens RSA da empresa
        response = supabase.table("cartoes_tokenizados").select("*").eq("empresa_id", empresa_id).execute()
        
        tokens = response.data or []
        migration_stats["processed"] = len(tokens)
        
        for token_data in tokens:
            try:
                # Verificar se já tem safe_card_data
                if token_data.get("safe_card_data"):
                    migration_stats["skipped"] += 1
                    continue
                
                encrypted_data = token_data.get("encrypted_card_data")
                if not encrypted_data:
                    migration_stats["skipped"] += 1
                    continue
                
                # Tentar descriptografar RSA
                decrypted = await _decrypt_card_data_rsa(empresa_id, encrypted_data)
                
                # Criar dados seguros
                from ..services.card_tokenization_service import CardTokenizationService
                service = CardTokenizationService()
                
                safe_token_data = service.create_card_token(empresa_id, {
                    "card_number": decrypted["card_number"],
                    "security_code": decrypted["security_code"],
                    "expiration_month": decrypted["expiration_month"],
                    "expiration_year": decrypted["expiration_year"],
                    "cardholder_name": token_data.get("cardholder_name", "")
                })
                
                # Atualizar registro
                supabase.table("cartoes_tokenizados").update({
                    "safe_card_data": json.dumps({
                        "cardholder_name": safe_token_data["cardholder_name"],
                        "last_four_digits": safe_token_data["last_four_digits"],
                        "card_brand": safe_token_data["card_brand"],
                        "expiration_month": safe_token_data["expiration_month"],
                        "expiration_year": safe_token_data["expiration_year"],
                        "card_hash": safe_token_data["card_hash"],
                        "tokenization_method": "migrated_from_rsa"
                    })
                }).eq("id", token_data["id"]).execute()
                
                migration_stats["migrated"] += 1
                
            except Exception as e:
                logger.error(f"❌ Erro ao migrar token {token_data.get('card_token')}: {e}")
                migration_stats["errors"] += 1
        
        logger.info(f"✅ Migração concluída para empresa {empresa_id}: {migration_stats}")
        return migration_stats
        
    except Exception as e:
        logger.error(f"❌ Erro na migração da empresa {empresa_id}: {e}")
        migration_stats["errors"] = migration_stats["processed"]
        return migration_stats


# ========== EXPORTS ==========

__all__ = [
    # Funções deprecated (compatibilidade)
    "encrypt_card_data",
    "decrypt_card_data", 
    "get_private_key",
    "get_public_key",
    
    # Funções novas (recomendadas)
    "tokenize_card_secure",
    "get_card_safe_data",
    "verify_card_with_token",
    
    # Helpers
    "migrate_rsa_to_simple",
]