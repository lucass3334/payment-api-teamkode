# payment_kode_api/app/services/company_encryption.py

import hashlib
import json
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet

from ..database.supabase_client import supabase
from ..utilities.logging_config import logger


class CompanyEncryptionService:
    """
    Serviço de criptografia por empresa para tokenização segura.
    
    ✅ Características:
    - Chave única e determinística por empresa
    - Criptografia AES-256 via Fernet
    - Hash de verificação de integridade
    - Compatível com qualquer gateway
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
        Resolve token interno para dados reais do cartão.
        
        Esta é a função principal que os gateways usarão para obter
        dados reais do cartão a partir do token interno.
        
        Args:
            empresa_id: ID da empresa
            card_token: Token interno do cartão
            
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
            
            # 2. Buscar chave da empresa
            decryption_key = await self.get_empresa_decryption_key(empresa_id)
            
            # 3. Descriptografar dados
            encrypted_data = card.get("encrypted_card_data")
            if not encrypted_data:
                raise ValueError("Dados criptografados não encontrados para o token")
            
            card_data = self.decrypt_card_data_with_company_key(encrypted_data, decryption_key)
            
            logger.info(f"✅ Token interno {card_token} resolvido para dados reais")
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
            import uuid
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
            
            # Obter chave da empresa
            company_key = await self.get_empresa_decryption_key(empresa_id)
            
            for token_data in tokens:
                try:
                    # Verificar se já foi migrado
                    if token_data.get("safe_card_data"):
                        migration_stats["skipped"] += 1
                        continue
                    
                    encrypted_data = token_data.get("encrypted_card_data")
                    if not encrypted_data:
                        migration_stats["skipped"] += 1
                        continue
                    
                    # Tentar descriptografar RSA (se ainda existir a função)
                    try:
                        from ..security.crypto import decrypt_card_data
                        decrypted = await decrypt_card_data(empresa_id, encrypted_data)
                        
                        # Re-criptografar com chave da empresa
                        new_encrypted = self.encrypt_card_data_with_company_key(decrypted, company_key)
                        
                        # Atualizar registro
                        supabase.table("cartoes_tokenizados").update({
                            "encrypted_card_data": new_encrypted,
                            "safe_card_data": {
                                "tokenization_method": "migrated_from_rsa",
                                "migration_date": datetime.now(timezone.utc).isoformat(),
                                "company_encryption": True
                            },
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", token_data["id"]).execute()
                        
                        migration_stats["migrated"] += 1
                        
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
            
            # Contar tokens
            tokens_response = (
                supabase.table("cartoes_tokenizados")
                .select("encrypted_card_data, safe_card_data")
                .eq("empresa_id", empresa_id)
                .execute()
            )
            
            for token in tokens_response.data or []:
                if token.get("encrypted_card_data"):
                    health["tokens_encrypted"] += 1
                
                safe_data = token.get("safe_card_data")
                if safe_data and isinstance(safe_data, dict):
                    if "migrated" in safe_data.get("tokenization_method", ""):
                        health["tokens_migrated"] += 1
            
            # Verificar se há problemas
            if not health["key_configured"]:
                health["issues"].append("Chave de criptografia não configurada")
            
            if health["tokens_encrypted"] == 0 and health["tokens_migrated"] == 0:
                health["issues"].append("Nenhum token encontrado para esta empresa")
            
            health["status"] = "healthy" if not health["issues"] else "warning"
            
            return health
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar saúde da criptografia: {e}")
            return {
                "empresa_id": empresa_id,
                "status": "error",
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat()
            }