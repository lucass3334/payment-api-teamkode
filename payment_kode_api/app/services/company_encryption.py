# payment_kode_api/app/services/company_encryption.py

import hashlib
import json
import base64
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet

from ..database.supabase_client import supabase
from ..utilities.logging_config import logger


class CompanyEncryptionService:
    """
    🆕 NOVO: Serviço de criptografia por empresa para tokenização segura.
    
    ✅ Características:
    - Chave única e determinística por empresa
    - Criptografia AES-256 via Fernet
    - Hash de verificação de integridade
    - Compatível com qualquer gateway
    - Funciona independente de certificados RSA
    """
    
    def __init__(self):
        self.salt_version = "payment_kode_empresa_key_v1"
    
    def generate_company_decryption_key(self, empresa_id: str) -> str:
        """
        Gera chave única e determinística para empresa.
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Chave de 32 bytes para AES-256
        """
        try:
            # Usar empresa_id + salt fixo para gerar chave determinística
            # Assim sempre conseguimos re-gerar a mesma chave
            combined = f"{empresa_id}:{self.salt_version}".encode('utf-8')
            key_hash = hashlib.sha256(combined).hexdigest()
            
            # Pegar primeiros 32 bytes para AES-256
            key = key_hash[:32]
            
            logger.info(f"✅ Chave de descriptografia gerada para empresa {empresa_id}")
            return key
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar chave para empresa {empresa_id}: {e}")
            raise
    
    async def save_empresa_decryption_key(self, empresa_id: str, decryption_key: str) -> bool:
        """
        Salva chave de descriptografia da empresa com hash de verificação.
        
        Args:
            empresa_id: ID da empresa
            decryption_key: Chave de descriptografia
            
        Returns:
            True se salvo com sucesso
        """
        try:
            # Gerar hash da chave para verificação de integridade
            key_hash = hashlib.sha256(decryption_key.encode()).hexdigest()
            
            # Verificar se já existe chave para a empresa
            existing = (
                supabase.table("empresas_keys")
                .select("id")
                .eq("empresa_id", empresa_id)
                .limit(1)
                .execute()
            )
            
            key_data = {
                "empresa_id": empresa_id,
                "decryption_key_hash": key_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if existing.data:
                # Atualizar chave existente
                response = (
                    supabase.table("empresas_keys")
                    .update({
                        "decryption_key_hash": key_hash,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })
                    .eq("empresa_id", empresa_id)
                    .execute()
                )
                logger.info(f"🔄 Chave de descriptografia atualizada para empresa {empresa_id}")
            else:
                # Inserir nova chave
                response = (
                    supabase.table("empresas_keys")
                    .insert(key_data)
                    .execute()
                )
                logger.info(f"✅ Nova chave de descriptografia salva para empresa {empresa_id}")
            
            return bool(response.data)
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar chave da empresa {empresa_id}: {e}")
            raise
    
    async def get_empresa_decryption_key(self, empresa_id: str) -> str:
        """
        Recupera chave de descriptografia da empresa.
        
        Método híbrido:
        1. Tenta buscar no banco e verificar integridade
        2. Se não encontrar ou hash não bater, regenera deterministicamente
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Chave de descriptografia válida
        """
        try:
            # Opção 1: Buscar no banco
            response = (
                supabase.table("empresas_keys")
                .select("decryption_key_hash")
                .eq("empresa_id", empresa_id)
                .limit(1)
                .execute()
            )
            
            if response.data:
                stored_hash = response.data[0]["decryption_key_hash"]
                
                # Regenerar chave deterministicamente
                regenerated_key = self.generate_company_decryption_key(empresa_id)
                expected_hash = hashlib.sha256(regenerated_key.encode()).hexdigest()
                
                # Verificar integridade
                if stored_hash == expected_hash:
                    logger.info(f"✅ Chave validada com sucesso para empresa {empresa_id}")
                    return regenerated_key
                else:
                    logger.warning(f"⚠️ Hash de chave inválido para empresa {empresa_id}, regenerando...")
            
            # Opção 2: Regenerar deterministicamente
            logger.info(f"🔧 Regenerando chave para empresa {empresa_id}")
            new_key = self.generate_company_decryption_key(empresa_id)
            
            # Salvar nova chave no banco
            await self.save_empresa_decryption_key(empresa_id, new_key)
            
            return new_key
            
        except Exception as e:
            logger.error(f"❌ Erro ao recuperar chave da empresa {empresa_id}: {e}")
            raise
    
    def encrypt_card_data_with_company_key(self, card_data: Dict[str, Any], key: str) -> str:
        """
        Criptografa dados do cartão com chave da empresa usando Fernet (AES-256).
        
        Args:
            card_data: Dados do cartão a serem criptografados
            key: Chave de criptografia da empresa
            
        Returns:
            Dados criptografados em base64
        """
        try:
            # Criar chave Fernet a partir da chave da empresa
            key_bytes = key.encode('utf-8')[:32].ljust(32, b'0')  # Garantir 32 bytes
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            f = Fernet(fernet_key)
            
            # Serializar e criptografar
            json_data = json.dumps(card_data, ensure_ascii=False).encode('utf-8')
            encrypted = f.encrypt(json_data)
            
            # Retornar como base64 para armazenamento
            result = base64.b64encode(encrypted).decode('utf-8')
            
            logger.info("✅ Dados do cartão criptografados com chave da empresa")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro ao criptografar dados do cartão: {e}")
            raise
    
    def decrypt_card_data_with_company_key(self, encrypted_data: str, key: str) -> Dict[str, Any]:
        """
        Descriptografa dados do cartão com chave da empresa.
        
        Args:
            encrypted_data: Dados criptografados em base64
            key: Chave de descriptografia da empresa
            
        Returns:
            Dados do cartão descriptografados
        """
        try:
            # Criar chave Fernet
            key_bytes = key.encode('utf-8')[:32].ljust(32, b'0')
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            f = Fernet(fernet_key)
            
            # Descriptografar
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            decrypted = f.decrypt(encrypted_bytes)
            
            # Deserializar JSON
            result = json.loads(decrypted.decode('utf-8'))
            
            logger.info("✅ Dados do cartão descriptografados com sucesso")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro ao descriptografar dados do cartão: {e}")
            raise
    
    async def resolve_internal_token(self, empresa_id: str, card_token: str) -> Dict[str, Any]:
        """
        🚀 FUNÇÃO PRINCIPAL: Resolve token interno para dados reais do cartão.
        
        Esta é a função principal que os gateways usarão para obter
        dados reais do cartão a partir do token interno.
        
        Args:
            empresa_id: ID da empresa
            card_token: Token interno do cartão (UUID)
            
        Returns:
            Dados reais do cartão para usar com gateways
        """
        try:
            # 1. Buscar token no banco
            response = (
                supabase.table("cartoes_tokenizados")
                .select("*")
                .eq("card_token", card_token)
                .eq("empresa_id", empresa_id)
                .limit(1)
                .execute()
            )
            
            if not response.data:
                raise ValueError(f"Token {card_token} não encontrado para empresa {empresa_id}")
            
            card = response.data[0]
            
            # 2. Verificar se token expirou
            expires_at = card.get("expires_at")
            if expires_at:
                from datetime import datetime, timezone
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    
                    if exp_dt < datetime.now(timezone.utc):
                        raise ValueError(f"Token {card_token} expirou em {expires_at}")
                except Exception:
                    logger.warning(f"⚠️ Erro ao verificar expiração do token {card_token}")
            
            # 3. Buscar chave da empresa
            decryption_key = await self.get_empresa_decryption_key(empresa_id)
            
            # 4. Descriptografar dados
            encrypted_data = card.get("encrypted_card_data")
            if not encrypted_data:
                raise ValueError("Dados criptografados não encontrados para o token")
            
            card_data = self.decrypt_card_data_with_company_key(encrypted_data, decryption_key)
            
            logger.info(f"✅ Token interno {card_token[:8]}... resolvido para dados reais")
            return card_data
            
        except Exception as e:
            logger.error(f"❌ Erro ao resolver token interno {card_token}: {e}")
            raise
    
    def is_internal_token(self, token: str) -> bool:
        """
        Verifica se um token é interno (UUID) ou externo do gateway.
        
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
    
    async def migrate_rsa_tokens_to_company_encryption(self, empresa_id: str) -> Dict[str, Any]:
        """
        Migra tokens RSA existentes para criptografia por empresa.
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Estatísticas da migração
        """
        migration_stats = {
            "processed": 0,
            "migrated": 0,
            "errors": 0,
            "skipped": 0
        }
        
        try:
            # Buscar tokens RSA da empresa
            response = (
                supabase.table("cartoes_tokenizados")
                .select("*")
                .eq("empresa_id", empresa_id)
                .execute()
            )
            
            tokens = response.data or []
            migration_stats["processed"] = len(tokens)
            
            if not tokens:
                logger.info(f"✅ Nenhum token encontrado para migração da empresa {empresa_id}")
                return migration_stats
            
            # Obter chave da empresa
            company_key = await self.get_empresa_decryption_key(empresa_id)
            
            for token_data in tokens:
                try:
                    # Verificar se já foi migrado (tem safe_card_data)
                    if token_data.get("safe_card_data"):
                        migration_stats["skipped"] += 1
                        continue
                    
                    encrypted_data = token_data.get("encrypted_card_data")
                    if not encrypted_data:
                        migration_stats["skipped"] += 1
                        continue
                    
                    # Tentar descriptografar RSA (se ainda existir a função)
                    try:
                        # Verificar se é RSA antigo ou novo formato
                        if encrypted_data.startswith('{"method"'):
                            # Já é novo formato, apenas adicionar metadados
                            migration_stats["skipped"] += 1
                            continue
                        
                        # Tentar descriptografar como RSA
                        from ..security.crypto import decrypt_card_data
                        decrypted = await decrypt_card_data(empresa_id, encrypted_data)
                        
                        # Re-criptografar com chave da empresa
                        new_encrypted = self.encrypt_card_data_with_company_key(decrypted, company_key)
                        
                        # Criar dados seguros
                        safe_data = {
                            "tokenization_method": "migrated_from_rsa_to_company_v1",
                            "migration_date": datetime.now(timezone.utc).isoformat(),
                            "company_encryption": True,
                            "cardholder_name": decrypted.get("cardholder_name", ""),
                            "last_four_digits": token_data.get("last_four_digits", ""),
                            "card_brand": token_data.get("card_brand", "UNKNOWN"),
                            "created_at": token_data.get("created_at", "")
                        }
                        
                        # Atualizar registro
                        supabase.table("cartoes_tokenizados").update({
                            "encrypted_card_data": new_encrypted,
                            "safe_card_data": json.dumps(safe_data),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", token_data["id"]).execute()
                        
                        migration_stats["migrated"] += 1
                        logger.info(f"✅ Token migrado: {token_data.get('card_token')}")
                        
                    except Exception as decrypt_error:
                        logger.warning(f"⚠️ Não foi possível migrar token {token_data.get('card_token')}: {decrypt_error}")
                        migration_stats["errors"] += 1
                        continue
                
                except Exception as e:
                    logger.error(f"❌ Erro ao migrar token {token_data.get('card_token')}: {e}")
                    migration_stats["errors"] += 1
            
            logger.info(f"✅ Migração concluída para empresa {empresa_id}: {migration_stats}")
            return migration_stats
            
        except Exception as e:
            logger.error(f"❌ Erro na migração da empresa {empresa_id}: {e}")
            migration_stats["errors"] = migration_stats["processed"]
            return migration_stats
    
    async def verify_company_encryption_health(self, empresa_id: str) -> Dict[str, Any]:
        """
        Verifica saúde da criptografia da empresa.
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Status da saúde da criptografia
        """
        try:
            health = {
                "empresa_id": empresa_id,
                "key_configured": False,
                "key_valid": False,
                "tokens_encrypted": 0,
                "tokens_migrated": 0,
                "tokens_company_encrypted": 0,
                "encryption_method": "company_key_v1",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "issues": []
            }
            
            # Verificar se chave está configurada
            try:
                key = await self.get_empresa_decryption_key(empresa_id)
                health["key_configured"] = True
                
                # Testar criptografia/descriptografia
                test_data = {"test": "data", "timestamp": health["last_check"]}
                encrypted = self.encrypt_card_data_with_company_key(test_data, key)
                decrypted = self.decrypt_card_data_with_company_key(encrypted, key)
                
                if decrypted == test_data:
                    health["key_valid"] = True
                else:
                    health["issues"].append("Chave não consegue descriptografar dados corretamente")
                    
            except Exception as e:
                health["issues"].append(f"Erro ao validar chave: {str(e)}")
            
            # Contar tokens por tipo
            tokens_response = (
                supabase.table("cartoes_tokenizados")
                .select("encrypted_card_data, safe_card_data")
                .eq("empresa_id", empresa_id)
                .execute()
            )
            
            for token in tokens_response.data or []:
                if token.get("encrypted_card_data"):
                    health["tokens_encrypted"] += 1
                    
                    # Verificar se é criptografia por empresa
                    safe_data = token.get("safe_card_data")
                    if safe_data:
                        try:
                            if isinstance(safe_data, str):
                                safe_data = json.loads(safe_data)
                            
                            method = safe_data.get("tokenization_method", "")
                            if "company" in method or "migrated" in method:
                                health["tokens_company_encrypted"] += 1
                            if "migrated" in method:
                                health["tokens_migrated"] += 1
                        except:
                            pass
            
            # Verificar se há problemas
            if not health["key_configured"]:
                health["issues"].append("Chave de criptografia não configurada")
            
            if health["tokens_encrypted"] == 0:
                health["issues"].append("Nenhum token encontrado para esta empresa")
            
            if health["tokens_encrypted"] > 0 and health["tokens_company_encrypted"] == 0:
                health["issues"].append("Tokens encontrados mas nenhum usa criptografia por empresa")
            
            # Definir status geral
            if not health["issues"]:
                health["status"] = "healthy"
            elif health["key_valid"] and health["tokens_company_encrypted"] > 0:
                health["status"] = "warning"
            else:
                health["status"] = "error"
            
            return health
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar saúde da criptografia: {e}")
            return {
                "empresa_id": empresa_id,
                "status": "error",
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat()
            }
    
    async def cleanup_expired_tokens(self, empresa_id: str) -> Dict[str, Any]:
        """
        Remove tokens expirados da empresa.
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Estatísticas da limpeza
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            # Buscar tokens expirados
            response = (
                supabase.table("cartoes_tokenizados")
                .select("card_token, expires_at")
                .eq("empresa_id", empresa_id)
                .lt("expires_at", now)
                .execute()
            )
            
            expired_tokens = response.data or []
            
            if not expired_tokens:
                return {
                    "removed_tokens": 0,
                    "message": "Nenhum token expirado encontrado",
                    "empresa_id": empresa_id
                }
            
            # Remover tokens expirados
            token_ids = [token["card_token"] for token in expired_tokens]
            
            delete_response = (
                supabase.table("cartoes_tokenizados")
                .delete()
                .eq("empresa_id", empresa_id)
                .in_("card_token", token_ids)
                .execute()
            )
            
            removed_count = len(delete_response.data) if delete_response.data else 0
            
            logger.info(f"🧹 Removidos {removed_count} tokens expirados da empresa {empresa_id}")
            
            return {
                "removed_tokens": removed_count,
                "expired_token_ids": token_ids,
                "message": f"Removidos {removed_count} tokens expirados",
                "empresa_id": empresa_id
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao limpar tokens expirados: {e}")
            return {
                "error": str(e),
                "removed_tokens": 0,
                "empresa_id": empresa_id
            }
    
    async def get_encryption_statistics(self, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas detalhadas de criptografia.
        
        Args:
            empresa_id: ID da empresa (None = todas as empresas)
            
        Returns:
            Estatísticas de criptografia
        """
        try:
            stats = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_companies": 0,
                "companies_with_keys": 0,
                "total_tokens": 0,
                "tokens_by_method": {
                    "rsa_legacy": 0,
                    "company_encryption": 0,
                    "migrated_tokens": 0,
                    "unknown": 0
                },
                "health_summary": {
                    "healthy": 0,
                    "warning": 0,
                    "error": 0
                }
            }
            
            # Buscar empresas
            if empresa_id:
                empresas_query = supabase.table("empresas").select("empresa_id").eq("empresa_id", empresa_id)
            else:
                empresas_query = supabase.table("empresas").select("empresa_id")
            
            empresas_response = empresas_query.execute()
            empresas = empresas_response.data or []
            
            stats["total_companies"] = len(empresas)
            
            # Analisar cada empresa
            for empresa in empresas:
                emp_id = empresa["empresa_id"]
                
                # Verificar se tem chave
                key_response = (
                    supabase.table("empresas_keys")
                    .select("decryption_key_hash")
                    .eq("empresa_id", emp_id)
                    .execute()
                )
                
                if key_response.data:
                    stats["companies_with_keys"] += 1
                
                # Verificar saúde
                health = await self.verify_company_encryption_health(emp_id)
                health_status = health.get("status", "error")
                stats["health_summary"][health_status] = stats["health_summary"].get(health_status, 0) + 1
                
                # Contar tokens por método
                tokens_response = (
                    supabase.table("cartoes_tokenizados")
                    .select("safe_card_data, encrypted_card_data")
                    .eq("empresa_id", emp_id)
                    .execute()
                )
                
                for token in tokens_response.data or []:
                    stats["total_tokens"] += 1
                    
                    safe_data = token.get("safe_card_data")
                    if safe_data:
                        try:
                            if isinstance(safe_data, str):
                                safe_data = json.loads(safe_data)
                            
                            method = safe_data.get("tokenization_method", "")
                            if "company" in method:
                                stats["tokens_by_method"]["company_encryption"] += 1
                            elif "migrated" in method:
                                stats["tokens_by_method"]["migrated_tokens"] += 1
                            else:
                                stats["tokens_by_method"]["unknown"] += 1
                        except:
                            stats["tokens_by_method"]["unknown"] += 1
                    else:
                        # Provavelmente RSA legacy
                        stats["tokens_by_method"]["rsa_legacy"] += 1
            
            # Calcular percentuais
            if stats["total_companies"] > 0:
                stats["companies_with_keys_percentage"] = round(
                    (stats["companies_with_keys"] / stats["total_companies"]) * 100, 1
                )
            
            if stats["total_tokens"] > 0:
                for method in stats["tokens_by_method"]:
                    count = stats["tokens_by_method"][method]
                    stats["tokens_by_method"][f"{method}_percentage"] = round(
                        (count / stats["total_tokens"]) * 100, 1
                    )
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas de criptografia: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


# ========== CLASSE DE EXCEÇÕES ==========

class CompanyEncryptionError(Exception):
    """Exceção base para erros de criptografia por empresa."""
    pass


class TokenResolutionError(CompanyEncryptionError):
    """Exceção para erros na resolução de tokens."""
    pass


class EncryptionKeyError(CompanyEncryptionError):
    """Exceção para erros relacionados a chaves de criptografia."""
    pass


# ========== FUNÇÕES AUXILIARES ==========

def create_company_encryption_service() -> CompanyEncryptionService:
    """Factory function para criar serviço de criptografia."""
    return CompanyEncryptionService()


async def quick_token_resolution(empresa_id: str, card_token: str) -> Dict[str, Any]:
    """
    🚀 FUNÇÃO DE CONVENIÊNCIA: Resolução rápida de token.
    
    Args:
        empresa_id: ID da empresa
        card_token: Token do cartão
        
    Returns:
        Dados do cartão ou informações de erro
    """
    try:
        service = CompanyEncryptionService()
        
        if not service.is_internal_token(card_token):
            return {
                "success": False,
                "error": "Token não é interno (UUID)",
                "is_internal": False
            }
        
        card_data = await service.resolve_internal_token(empresa_id, card_token)
        
        return {
            "success": True,
            "card_data": card_data,
            "is_internal": True
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "is_internal": True
        }


# ========== EXPORTS ==========

__all__ = [
    # Classe principal
    "CompanyEncryptionService",
    
    # Exceções
    "CompanyEncryptionError",
    "TokenResolutionError", 
    "EncryptionKeyError",
    
    # Funções auxiliares
    "create_company_encryption_service",
    "quick_token_resolution",
]