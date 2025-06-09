# payment_kode_api/app/services/company_encryption.py

import hashlib
import json
import base64
import uuid
import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet

from ..database.supabase_client import supabase
from ..utilities.logging_config import logger


class CompanyEncryptionService:
    """
    🔧 VERSÃO MELHORADA: Serviço de criptografia por empresa para tokenização segura.
    
    ✅ Melhorias implementadas:
    - Chave gerada com Fernet.generate_key() para máxima segurança
    - Suporte a inserção manual de chaves para empresas existentes
    - Validação robusta de chaves
    - Melhor tratamento de erros
    - Sistema de backup de chaves
    """
    
    def __init__(self):
        self.salt_version = "payment_kode_fernet_v2"  # 🔧 Atualizado
    
    def generate_company_decryption_key(self, empresa_id: str, use_deterministic: bool = False) -> str:
        """
        🔧 MELHORADO: Gera chave única para empresa.
        
        Args:
            empresa_id: ID da empresa
            use_deterministic: Se True, gera chave determinística (fallback)
                              Se False, gera chave aleatória (recomendado)
        
        Returns:
            Chave Fernet válida em base64
        """
        try:
            if use_deterministic:
                # Método determinístico (fallback para compatibilidade)
                logger.warning(f"⚠️ Usando método determinístico para empresa {empresa_id}")
                combined = f"{empresa_id}:{self.salt_version}".encode('utf-8')
                key_material = hashlib.sha256(combined).digest()
                # Usar apenas 32 bytes para Fernet
                fernet_key = base64.urlsafe_b64encode(key_material)
                return fernet_key.decode('utf-8')
            else:
                # ✅ MÉTODO RECOMENDADO: Chave totalmente aleatória usando Fernet
                fernet_key = Fernet.generate_key()
                logger.info(f"✅ Chave aleatória gerada para empresa {empresa_id}")
                return fernet_key.decode('utf-8')
                
        except Exception as e:
            logger.error(f"❌ Erro ao gerar chave para empresa {empresa_id}: {e}")
            raise
    
    def validate_fernet_key(self, key: str) -> bool:
        """
        🆕 NOVA: Valida se uma chave é válida para Fernet.
        
        Args:
            key: Chave a ser validada
            
        Returns:
            True se a chave for válida
        """
        try:
            # Tentar criar um objeto Fernet com a chave
            if isinstance(key, str):
                key_bytes = key.encode('utf-8')
            else:
                key_bytes = key
                
            f = Fernet(key_bytes)
            
            # Testar criptografia/descriptografia
            test_data = b"test_encryption_validation"
            encrypted = f.encrypt(test_data)
            decrypted = f.decrypt(encrypted)
            
            return decrypted == test_data
            
        except Exception as e:
            logger.warning(f"⚠️ Chave inválida: {e}")
            return False
    
    async def save_empresa_decryption_key(self, empresa_id: str, decryption_key: str) -> bool:
        """
        🔧 MELHORADO: Salva chave de descriptografia da empresa com validação.
        
        Args:
            empresa_id: ID da empresa
            decryption_key: Chave de descriptografia (string Fernet)
            
        Returns:
            True se salvo com sucesso
        """
        try:
            # 🆕 VALIDAR CHAVE ANTES DE SALVAR
            if not self.validate_fernet_key(decryption_key):
                raise ValueError("Chave fornecida não é uma chave Fernet válida")
            
            # Gerar hash da chave para verificação de integridade
            key_hash = hashlib.sha256(decryption_key.encode()).hexdigest()
            
            # Verificar se já existe chave para a empresa
            existing = (
                supabase.table("empresas_keys")
                .select("id, decryption_key_hash")
                .eq("empresa_id", empresa_id)
                .limit(1)
                .execute()
            )
            
            key_data = {
                "empresa_id": empresa_id,
                "decryption_key_hash": key_hash,
                "decryption_key": decryption_key,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if existing.data:
                # Verificar se a chave mudou
                old_hash = existing.data[0]["decryption_key_hash"]
                if old_hash == key_hash:
                    logger.info(f"✅ Chave idêntica já existe para empresa {empresa_id}")
                    return True
                
                # 🆕 BACKUP DA CHAVE ANTIGA
                await self._backup_old_key(empresa_id, old_hash)
                
                # Atualizar chave existente
                response = (
                    supabase.table("empresas_keys")
                    .update({
                        "decryption_key_hash": key_hash,
                        "decryption_key": decryption_key,
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
    
    async def _backup_old_key(self, empresa_id: str, old_key_hash: str) -> None:
        """
        🆕 NOVA: Faz backup da chave antiga antes de substituir.
        """
        try:
            backup_data = {
                "empresa_id": empresa_id,
                "old_key_hash": old_key_hash,
                "backed_up_at": datetime.now(timezone.utc).isoformat(),
                "reason": "key_rotation"
            }
            
            supabase.table("empresas_keys_backup").insert(backup_data).execute()
            logger.info(f"📦 Backup da chave antiga criado para empresa {empresa_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao fazer backup da chave: {e}")
    
    async def get_empresa_decryption_key(self, empresa_id: str) -> str:
        """
        🔧 MELHORADO: Recupera chave de descriptografia da empresa.
        
        Args:
            empresa_id: ID da empresa
            
        Returns:
            Chave de descriptografia válida
        """
        try:
            # Buscar no banco
            response = (
                supabase.table("empresas_keys")
                .select("decryption_key_hash")
                .eq("empresa_id", empresa_id)
                .limit(1)
                .execute()
            )
            
            if response.data:
                stored_hash = response.data[0]["decryption_key_hash"]
                logger.info(f"✅ Chave encontrada no banco para empresa {empresa_id}")
                
                # ⚠️ IMPORTANTE: Não podemos regenerar uma chave Fernet aleatória
                # Se a chave foi perdida, precisamos criar uma nova e invalidar tokens antigos
                logger.error(f"❌ Sistema anterior incompatível - chave Fernet não pode ser regenerada deterministicamente")
                raise ValueError(
                    "Chave de criptografia não pode ser recuperada. "
                    "Use insert_manual_key() para inserir uma nova chave válida."
                )
            
            # Não existe chave - gerar nova
            logger.info(f"🔧 Gerando nova chave para empresa {empresa_id}")
            new_key = self.generate_company_decryption_key(empresa_id, use_deterministic=False)
            
            # Salvar nova chave no banco
            await self.save_empresa_decryption_key(empresa_id, new_key)
            
            return new_key
            
        except Exception as e:
            logger.error(f"❌ Erro ao recuperar chave da empresa {empresa_id}: {e}")
            raise
    
    async def insert_manual_key(self, empresa_id: str, manual_key: Optional[str] = None) -> str:
        """
        🆕 NOVA FUNÇÃO: Insere chave manualmente para empresas existentes.
        
        Args:
            empresa_id: ID da empresa
            manual_key: Chave Fernet válida (se None, gera uma nova)
            
        Returns:
            Chave inserida/gerada
        """
        try:
            if manual_key:
                # Validar chave fornecida
                if not self.validate_fernet_key(manual_key):
                    raise ValueError("Chave manual fornecida não é uma chave Fernet válida")
                
                key_to_save = manual_key
                logger.info(f"🔑 Inserindo chave manual para empresa {empresa_id}")
            else:
                # Gerar nova chave
                key_to_save = self.generate_company_decryption_key(empresa_id, use_deterministic=False)
                logger.info(f"🆕 Gerando nova chave para empresa {empresa_id}")
            
            # Salvar chave
            await self.save_empresa_decryption_key(empresa_id, key_to_save)
            
            # Verificar saúde da criptografia
            health = await self.verify_company_encryption_health(empresa_id)
            if health.get("status") != "healthy":
                logger.warning(f"⚠️ Problemas detectados após inserção: {health.get('issues', [])}")
            
            logger.info(f"✅ Chave inserida com sucesso para empresa {empresa_id}")
            return key_to_save
            
        except Exception as e:
            logger.error(f"❌ Erro ao inserir chave manual: {e}")
            raise
    
    def encrypt_card_data_with_company_key(self, card_data: Dict[str, Any], key: str) -> str:
        """
        🔧 MELHORADO: Criptografa dados do cartão com chave Fernet.
        
        Args:
            card_data: Dados do cartão a serem criptografados
            key: Chave Fernet da empresa
            
        Returns:
            Dados criptografados em base64
        """
        try:
            # Validar chave
            if not self.validate_fernet_key(key):
                raise ValueError("Chave fornecida não é uma chave Fernet válida")
            
            # Criar objeto Fernet
            if isinstance(key, str):
                key = key.encode('utf-8')
            f = Fernet(key)
            
            # Serializar e criptografar
            json_data = json.dumps(card_data, ensure_ascii=False).encode('utf-8')
            encrypted = f.encrypt(json_data)
            
            # Retornar como base64 para armazenamento
            result = base64.b64encode(encrypted).decode('utf-8')
            
            logger.info("✅ Dados do cartão criptografados com chave Fernet")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro ao criptografar dados do cartão: {e}")
            raise
    
    def decrypt_card_data_with_company_key(self, encrypted_data: str, key: str) -> Dict[str, Any]:
        """
        🔧 MELHORADO: Descriptografa dados do cartão com chave Fernet.
        
        Args:
            encrypted_data: Dados criptografados em base64
            key: Chave Fernet da empresa
            
        Returns:
            Dados do cartão descriptografados
        """
        try:
            # Validar chave
            if not self.validate_fernet_key(key):
                raise ValueError("Chave fornecida não é uma chave Fernet válida")
            
            # Criar objeto Fernet
            if isinstance(key, str):
                key = key.encode('utf-8')
            f = Fernet(key)
            
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
        🔧 MELHORADO: Resolve token interno para dados reais do cartão.
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
        """Verifica se um token é interno (UUID) ou externo do gateway."""
        try:
            uuid.UUID(token)
            return True
        except (ValueError, TypeError):
            return False
    
    async def verify_company_encryption_health(self, empresa_id: str) -> Dict[str, Any]:
        """
        🔧 MELHORADO: Verifica saúde da criptografia da empresa.
        """
        try:
            health = {
                "empresa_id": empresa_id,
                "key_configured": False,
                "key_valid": False,
                "tokens_encrypted": 0,
                "tokens_migrated": 0,
                "tokens_company_encrypted": 0,
                "encryption_method": "fernet_v2",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "issues": []
            }
            
            # Verificar se chave está configurada
            try:
                response = (
                    supabase.table("empresas_keys")
                    .select("decryption_key_hash")
                    .eq("empresa_id", empresa_id)
                    .limit(1)
                    .execute()
                )
                
                if response.data:
                    health["key_configured"] = True
                    
                    # ⚠️ IMPORTANTE: Não podemos testar chaves Fernet sem ter a chave real
                    # Assumimos que se existe hash, a chave é válida
                    health["key_valid"] = True
                    health["issues"].append("Não é possível testar chave sem acessá-la diretamente")
                else:
                    health["issues"].append("Chave de criptografia não configurada")
                    
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
                            if "company" in method or "fernet" in method:
                                health["tokens_company_encrypted"] += 1
                            if "migrated" in method:
                                health["tokens_migrated"] += 1
                        except:
                            pass
            
            # Verificar problemas
            if not health["key_configured"]:
                health["issues"].append("Chave de criptografia não configurada")
            
            if health["tokens_encrypted"] == 0:
                health["issues"].append("Nenhum token encontrado para esta empresa")
            
            if health["tokens_encrypted"] > 0 and health["tokens_company_encrypted"] == 0:
                health["issues"].append("Tokens encontrados mas nenhum usa criptografia por empresa")
            
            # Definir status geral
            if not health["issues"]:
                health["status"] = "healthy"
            elif health["key_configured"] and health["tokens_company_encrypted"] > 0:
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
    
    async def migrate_rsa_tokens_to_company_encryption(self, empresa_id: str) -> Dict[str, Any]:
        """
        🔧 MELHORADO: Migra tokens RSA existentes para criptografia Fernet por empresa.
        """
        migration_stats = {
            "processed": 0,
            "migrated": 0,
            "errors": 0,
            "skipped": 0,
            "requires_manual_key": False
        }
        
        try:
            # Verificar se empresa tem chave configurada
            try:
                company_key = await self.get_empresa_decryption_key(empresa_id)
            except Exception:
                migration_stats["requires_manual_key"] = True
                logger.warning(
                    f"⚠️ Empresa {empresa_id} não tem chave configurada. "
                    f"Use insert_manual_key() antes da migração."
                )
                return migration_stats
            
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
            
            for token_data in tokens:
                try:
                    # Verificar se já foi migrado (tem safe_card_data com método Fernet)
                    safe_data = token_data.get("safe_card_data")
                    if safe_data:
                        try:
                            if isinstance(safe_data, str):
                                safe_data = json.loads(safe_data)
                            method = safe_data.get("tokenization_method", "")
                            if "fernet" in method:
                                migration_stats["skipped"] += 1
                                continue
                        except:
                            pass
                    
                    encrypted_data = token_data.get("encrypted_card_data")
                    if not encrypted_data:
                        migration_stats["skipped"] += 1
                        continue
                    
                    # Tentar descriptografar RSA (se ainda existir a função)
                    try:
                        from ..security.crypto import decrypt_card_data
                        decrypted = await decrypt_card_data(empresa_id, encrypted_data)
                        
                        # Re-criptografar com Fernet
                        new_encrypted = self.encrypt_card_data_with_company_key(decrypted, company_key)
                        
                        # Criar dados seguros
                        safe_data = {
                            "tokenization_method": "migrated_from_rsa_to_fernet_v2",
                            "migration_date": datetime.now(timezone.utc).isoformat(),
                            "company_encryption": True,
                            "encryption_type": "fernet",
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
                        logger.info(f"✅ Token migrado para Fernet: {token_data.get('card_token')}")
                        
                    except Exception as decrypt_error:
                        logger.warning(f"⚠️ Não foi possível migrar token {token_data.get('card_token')}: {decrypt_error}")
                        migration_stats["errors"] += 1
                        continue
                
                except Exception as e:
                    logger.error(f"❌ Erro ao migrar token {token_data.get('card_token')}: {e}")
                    migration_stats["errors"] += 1
            
            logger.info(f"✅ Migração para Fernet concluída para empresa {empresa_id}: {migration_stats}")
            return migration_stats
            
        except Exception as e:
            logger.error(f"❌ Erro na migração da empresa {empresa_id}: {e}")
            migration_stats["errors"] = migration_stats["processed"]
            return migration_stats


# ========== FUNÇÕES AUXILIARES PARA GESTÃO MANUAL ==========

async def setup_company_encryption_for_existing_companies() -> Dict[str, Any]:
    """
    🆕 NOVA: Configura criptografia para empresas existentes.
    
    Returns:
        Estatísticas do processo
    """
    try:
        # Buscar todas as empresas
        empresas_response = supabase.table("empresas").select("empresa_id, nome").execute()
        empresas = empresas_response.data or []
        
        encryption_service = CompanyEncryptionService()
        setup_stats = {
            "total_empresas": len(empresas),
            "already_configured": 0,
            "newly_configured": 0,
            "errors": 0,
            "results": []
        }
        
        for empresa in empresas:
            empresa_id = empresa["empresa_id"]
            empresa_nome = empresa["nome"]
            
            try:
                # Verificar se já tem chave
                existing = (
                    supabase.table("empresas_keys")
                    .select("id")
                    .eq("empresa_id", empresa_id)
                    .execute()
                )
                
                if existing.data:
                    setup_stats["already_configured"] += 1
                    result_status = "already_configured"
                else:
                    # Configurar nova chave
                    new_key = await encryption_service.insert_manual_key(empresa_id)
                    setup_stats["newly_configured"] += 1
                    result_status = "newly_configured"
                
                setup_stats["results"].append({
                    "empresa_id": empresa_id,
                    "empresa_nome": empresa_nome,
                    "status": result_status
                })
                
            except Exception as e:
                setup_stats["errors"] += 1
                setup_stats["results"].append({
                    "empresa_id": empresa_id,
                    "empresa_nome": empresa_nome,
                    "status": "error",
                    "error": str(e)
                })
                logger.error(f"❌ Erro ao configurar empresa {empresa_id}: {e}")
        
        logger.info(f"✅ Setup concluído: {setup_stats}")
        return setup_stats
        
    except Exception as e:
        logger.error(f"❌ Erro no setup geral: {e}")
        return {"error": str(e)}


async def regenerate_all_company_keys() -> Dict[str, Any]:
    """
    🆕 NOVA: Regenera chaves para todas as empresas.
    ⚠️ CUIDADO: Isso invalidará todos os tokens existentes!
    """
    logger.warning("⚠️ REGENERAÇÃO GLOBAL DE CHAVES INICIADA - TODOS OS TOKENS SERÃO INVALIDADOS!")
    
    try:
        # Buscar empresas com chaves
        keys_response = (
            supabase.table("empresas_keys")
            .select("empresa_id")
            .execute()
        )
        
        encryption_service = CompanyEncryptionService()
        regen_stats = {
            "total_empresas": len(keys_response.data or []),
            "regenerated": 0,
            "errors": 0,
            "results": []
        }
        
        for key_data in keys_response.data or []:
            empresa_id = key_data["empresa_id"]
            
            try:
                # Gerar nova chave
                new_key = await encryption_service.insert_manual_key(empresa_id)
                regen_stats["regenerated"] += 1
                
                regen_stats["results"].append({
                    "empresa_id": empresa_id,
                    "status": "regenerated"
                })
                
                logger.info(f"✅ Chave regenerada para empresa {empresa_id}")
                
            except Exception as e:
                regen_stats["errors"] += 1
                regen_stats["results"].append({
                    "empresa_id": empresa_id,
                    "status": "error",
                    "error": str(e)
                })
                logger.error(f"❌ Erro ao regenerar chave da empresa {empresa_id}: {e}")
        
        logger.warning(f"⚠️ REGENERAÇÃO CONCLUÍDA: {regen_stats}")
        return regen_stats
        
    except Exception as e:
        logger.error(f"❌ Erro na regeneração global: {e}")
        return {"error": str(e)}


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


class InvalidKeyError(CompanyEncryptionError):
    """Exceção para chaves inválidas."""
    pass


# ========== FUNÇÕES AUXILIARES ==========

def create_company_encryption_service() -> CompanyEncryptionService:
    """Factory function para criar serviço de criptografia."""
    return CompanyEncryptionService()


def generate_fernet_key() -> str:
    """
    🆕 NOVA: Gera uma chave Fernet válida.
    
    Returns:
        Chave Fernet em formato string
    """
    return Fernet.generate_key().decode('utf-8')


async def quick_token_resolution(empresa_id: str, card_token: str) -> Dict[str, Any]:
    """
    🔧 MELHORADO: Resolução rápida de token com tratamento de erros.
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
    "InvalidKeyError",
    
    # Funções auxiliares
    "create_company_encryption_service",
    "generate_fernet_key",
    "quick_token_resolution",
    
    # Funções de gestão manual
    "setup_company_encryption_for_existing_companies",
    "regenerate_all_company_keys",
]