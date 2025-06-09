# payment_kode_api/app/api/routes/encryption_admin.py

from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

from ...services.company_encryption import (
    CompanyEncryptionService,
    setup_company_encryption_for_existing_companies,
    regenerate_all_company_keys,
    generate_fernet_key,
)
from ...security.auth import validate_access_token
from ...utilities.logging_config import logger

router = APIRouter(tags=["Administração de Criptografia"], dependencies=[Depends(validate_access_token)])


# ========== SCHEMAS ==========

class InsertKeyRequest(BaseModel):
    """Schema para inserção manual de chave."""
    empresa_id: str = Field(..., description="ID da empresa")
    manual_key: Optional[str] = Field(None, description="Chave Fernet (se None, gera nova)")
    force_replace: bool = Field(False, description="Forçar substituição se já existir")


class InsertKeyResponse(BaseModel):
    """Resposta da inserção de chave."""
    success: bool
    message: str
    empresa_id: str
    key_inserted: bool
    key_preview: str  # Primeiros 16 caracteres da chave
    health_status: Dict[str, Any]


class MigrationRequest(BaseModel):
    """Schema para migração de tokens."""
    empresa_id: str = Field(..., description="ID da empresa")
    dry_run: bool = Field(True, description="Apenas simular migração")


class BatchKeySetupRequest(BaseModel):
    """Schema para setup em lote."""
    empresa_ids: Optional[List[str]] = Field(None, description="IDs específicas (se None, todas)")
    dry_run: bool = Field(True, description="Apenas simular")


class HealthCheckResponse(BaseModel):
    """Resposta do health check."""
    empresa_id: str
    status: str
    key_configured: bool
    key_valid: bool
    tokens_encrypted: int
    tokens_company_encrypted: int
    issues: List[str]
    last_check: str

class GenerateKeyResponse(BaseModel):
    fernet_key: str
    key_preview: str
    key_length: int
    message: str
    warning: str
# ========== ENDPOINTS DE ADMINISTRAÇÃO ==========

@router.post("/encryption/generate-key", response_model=GenerateKeyResponse, summary="Gera nova chave Fernet")
async def generate_new_fernet_key():
   
    try:
        new_key = generate_fernet_key()
        
        return {
            "fernet_key": new_key,
            "key_preview": new_key[:16] + "...",
            "key_length": len(new_key),
            "message": "Chave gerada com sucesso. Guarde-a em local seguro!",
            "warning": "Esta chave não será mostrada novamente. Salve-a imediatamente!"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar chave: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar chave: {str(e)}")


@router.post("/encryption/insert-key", response_model=InsertKeyResponse)
async def insert_company_key(
    request: InsertKeyRequest,
    # Remover validação de token para admin - ou criar sistema de admin separado
    # empresa: dict = Depends(validate_access_token)
):
    """
    🔧 Insere chave de criptografia manualmente para uma empresa.
    
    Casos de uso:
    - Empresas existentes sem chave configurada
    - Substituição de chaves comprometidas
    - Migração de sistemas legados
    """
    try:
        encryption_service = CompanyEncryptionService()
        
        # Verificar se empresa existe
        from ...database.supabase_client import supabase
        empresa_check = (
            supabase.table("empresas")
            .select("empresa_id, nome")
            .eq("empresa_id", request.empresa_id)
            .execute()
        )
        
        if not empresa_check.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        
        empresa_nome = empresa_check.data[0]["nome"]
        
        # Verificar se já tem chave (se não forçar substituição)
        if not request.force_replace:
            existing_key = (
                supabase.table("empresas_keys")
                .select("id")
                .eq("empresa_id", request.empresa_id)
                .execute()
            )
            
            if existing_key.data:
                raise HTTPException(
                    status_code=400, 
                    detail="Empresa já possui chave configurada. Use force_replace=true para substituir."
                )
        
        # Inserir chave
        inserted_key = await encryption_service.insert_manual_key(
            request.empresa_id, 
            request.manual_key
        )
        
        # Verificar saúde após inserção
        health_status = await encryption_service.verify_company_encryption_health(request.empresa_id)
        
        logger.info(f"✅ Chave inserida manualmente para empresa {request.empresa_id} ({empresa_nome})")
        
        return InsertKeyResponse(
            success=True,
            message=f"Chave inserida com sucesso para {empresa_nome}",
            empresa_id=request.empresa_id,
            key_inserted=True,
            key_preview=inserted_key[:16] + "...",
            health_status=health_status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao inserir chave: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/encryption/health/{empresa_id}", response_model=HealthCheckResponse)
async def check_encryption_health(
    empresa_id: str,
    # empresa: dict = Depends(validate_access_token)
):
    """
    🏥 Verifica saúde da criptografia de uma empresa específica.
    """
    try:
        encryption_service = CompanyEncryptionService()
        health = await encryption_service.verify_company_encryption_health(empresa_id)
        
        return HealthCheckResponse(
            empresa_id=health["empresa_id"],
            status=health["status"],
            key_configured=health["key_configured"],
            key_valid=health["key_valid"],
            tokens_encrypted=health["tokens_encrypted"],
            tokens_company_encrypted=health["tokens_company_encrypted"],
            issues=health["issues"],
            last_check=health["last_check"]
        )
        
    except Exception as e:
        logger.error(f"❌ Erro no health check: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no health check: {str(e)}")


@router.post("/encryption/migrate-tokens")
async def migrate_company_tokens(
    request: MigrationRequest,
    # empresa: dict = Depends(validate_access_token)
):
    """
    🔄 Migra tokens RSA de uma empresa para criptografia Fernet.
    """
    try:
        encryption_service = CompanyEncryptionService()
        
        if request.dry_run:
            # Apenas verificar o que seria migrado
            from ...database.supabase_client import supabase
            tokens_response = (
                supabase.table("cartoes_tokenizados")
                .select("id, card_token, safe_card_data")
                .eq("empresa_id", request.empresa_id)
                .execute()
            )
            
            tokens = tokens_response.data or []
            migration_needed = 0
            already_migrated = 0
            
            for token in tokens:
                safe_data = token.get("safe_card_data")
                if safe_data:
                    try:
                        if isinstance(safe_data, str):
                            import json
                            safe_data = json.loads(safe_data)
                        
                        method = safe_data.get("tokenization_method", "")
                        if "fernet" in method:
                            already_migrated += 1
                        else:
                            migration_needed += 1
                    except:
                        migration_needed += 1
                else:
                    migration_needed += 1
            
            return {
                "dry_run": True,
                "empresa_id": request.empresa_id,
                "total_tokens": len(tokens),
                "migration_needed": migration_needed,
                "already_migrated": already_migrated,
                "message": f"Migração simulada: {migration_needed} tokens precisam ser migrados"
            }
        else:
            # Executar migração real
            migration_stats = await encryption_service.migrate_rsa_tokens_to_company_encryption(request.empresa_id)
            
            return {
                "dry_run": False,
                "empresa_id": request.empresa_id,
                "migration_stats": migration_stats,
                "message": "Migração executada com sucesso"
            }
        
    except Exception as e:
        logger.error(f"❌ Erro na migração: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na migração: {str(e)}")


@router.post("/encryption/batch-setup")
async def batch_setup_encryption(
    request: BatchKeySetupRequest,
    # empresa: dict = Depends(validate_access_token)
):
    """
    🏭 Configura criptografia em lote para empresas existentes.
    
    Útil para setup inicial do sistema em empresas já cadastradas.
    """
    try:
        if request.empresa_ids:
            # Setup para empresas específicas
            from ...database.supabase_client import supabase
            encryption_service = CompanyEncryptionService()
            
            results = []
            
            for empresa_id in request.empresa_ids:
                try:
                    # Verificar se empresa existe
                    empresa_check = (
                        supabase.table("empresas")
                        .select("empresa_id, nome")
                        .eq("empresa_id", empresa_id)
                        .execute()
                    )
                    
                    if not empresa_check.data:
                        results.append({
                            "empresa_id": empresa_id,
                            "status": "not_found",
                            "message": "Empresa não encontrada"
                        })
                        continue
                    
                    if request.dry_run:
                        # Apenas verificar se precisa de setup
                        existing = (
                            supabase.table("empresas_keys")
                            .select("id")
                            .eq("empresa_id", empresa_id)
                            .execute()
                        )
                        
                        status = "already_configured" if existing.data else "needs_setup"
                        results.append({
                            "empresa_id": empresa_id,
                            "empresa_nome": empresa_check.data[0]["nome"],
                            "status": status
                        })
                    else:
                        # Executar setup real
                        await encryption_service.insert_manual_key(empresa_id)
                        results.append({
                            "empresa_id": empresa_id,
                            "empresa_nome": empresa_check.data[0]["nome"],
                            "status": "configured"
                        })
                        
                except Exception as e:
                    results.append({
                        "empresa_id": empresa_id,
                        "status": "error",
                        "error": str(e)
                    })
            
            return {
                "dry_run": request.dry_run,
                "batch_type": "specific_companies",
                "total_companies": len(request.empresa_ids),
                "results": results
            }
        else:
            # Setup para todas as empresas
            if request.dry_run:
                # Apenas contar quantas precisam
                from ...database.supabase_client import supabase
                
                empresas_response = supabase.table("empresas").select("empresa_id, nome").execute()
                keys_response = supabase.table("empresas_keys").select("empresa_id").execute()
                
                total_empresas = len(empresas_response.data or [])
                empresas_com_chave = len(keys_response.data or [])
                empresas_sem_chave = total_empresas - empresas_com_chave
                
                return {
                    "dry_run": True,
                    "batch_type": "all_companies",
                    "total_companies": total_empresas,
                    "already_configured": empresas_com_chave,
                    "needs_setup": empresas_sem_chave,
                    "message": f"{empresas_sem_chave} empresas precisam de configuração"
                }
            else:
                # Executar setup completo
                setup_stats = await setup_company_encryption_for_existing_companies()
                
                return {
                    "dry_run": False,
                    "batch_type": "all_companies",
                    "setup_stats": setup_stats,
                    "message": "Setup em lote executado"
                }
        
    except Exception as e:
        logger.error(f"❌ Erro no setup em lote: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no setup em lote: {str(e)}")


@router.get("/encryption/global-health")
async def get_global_encryption_health():
    """
    🌍 Verifica saúde global da criptografia de todas as empresas.
    """
    try:
        encryption_service = CompanyEncryptionService()
        stats = await encryption_service.get_encryption_statistics()
        
        return {
            "global_health": stats,
            "summary": {
                "total_companies": stats.get("total_companies", 0),
                "companies_with_keys": stats.get("companies_with_keys", 0),
                "health_distribution": stats.get("health_summary", {}),
                "encryption_coverage": f"{round((stats.get('companies_with_keys', 0) / max(stats.get('total_companies', 1), 1)) * 100, 1)}%"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no health check global: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no health check global: {str(e)}")


"""@router.post("/encryption/emergency-regenerate")
async def emergency_regenerate_all_keys():
    "
    🚨 EMERGÊNCIA: Regenera todas as chaves do sistema.
    
    ⚠️ ATENÇÃO: Isso invalidará TODOS os tokens existentes!
    Use apenas em caso de comprometimento de segurança.
    "
    try:
        logger.warning("🚨 REGENERAÇÃO EMERGENCIAL DE TODAS AS CHAVES INICIADA!")
        
        regen_stats = await regenerate_all_company_keys()
        
        return {
            "emergency_action": "regenerate_all_keys",
            "warning": "TODOS os tokens foram invalidados",
            "regeneration_stats": regen_stats,
            "next_steps": [
                "Notificar todos os clientes sobre invalidação de tokens",
                "Executar migração de tokens em todas as empresas",
                "Verificar saúde de todas as empresas",
                "Atualizar documentação de segurança"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erro na regeneração emergencial: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na regeneração emergencial: {str(e)}")"""


# ========== ENDPOINTS DE CONSULTA ==========

@router.get("/encryption/companies-status")
async def list_companies_encryption_status():
    """
    📋 Lista status de criptografia de todas as empresas.
    """
    try:
        from ...database.supabase_client import supabase
        
        # Buscar empresas
        empresas_response = supabase.table("empresas").select("empresa_id, nome, created_at").execute()
        empresas = empresas_response.data or []
        
        # Buscar chaves
        keys_response = supabase.table("empresas_keys").select("empresa_id, created_at as key_created_at").execute()
        empresas_com_chave = {k["empresa_id"]: k for k in keys_response.data or []}
        
        results = []
        
        for empresa in empresas:
            empresa_id = empresa["empresa_id"]
            key_info = empresas_com_chave.get(empresa_id)
            
            results.append({
                "empresa_id": empresa_id,
                "empresa_nome": empresa["nome"],
                "empresa_created_at": empresa["created_at"],
                "has_encryption_key": bool(key_info),
                "key_created_at": key_info["key_created_at"] if key_info else None,
                "status": "configured" if key_info else "needs_setup"
            })
        
        # Estatísticas
        total = len(results)
        configured = len([r for r in results if r["has_encryption_key"]])
        
        return {
            "companies": results,
            "summary": {
                "total": total,
                "configured": configured,
                "needs_setup": total - configured,
                "coverage_percentage": round((configured / total * 100), 1) if total > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar status: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar status: {str(e)}")


# ========== ENDPOINTS DE TESTE ==========

@router.post("/encryption/test-token-resolution")
async def test_token_resolution(
    empresa_id: str = Body(...),
    card_token: str = Body(...),
    # empresa: dict = Depends(validate_access_token)
):
    """
    🧪 Testa resolução de token interno para debugging.
    
    ⚠️ ATENÇÃO: Este endpoint retorna dados sensíveis!
    Use apenas para testes e debugging.
    """
    try:
        from ...services.company_encryption import quick_token_resolution
        
        result = await quick_token_resolution(empresa_id, card_token)
        
        if result["success"]:
            # ⚠️ MASCARAR DADOS SENSÍVEIS NO RETORNO
            card_data = result["card_data"]
            safe_result = {
                "success": True,
                "token_resolved": True,
                "card_info": {
                    "cardholder_name": card_data.get("cardholder_name", "N/A"),
                    "card_number_masked": f"****-****-****-{card_data.get('card_number', '')[-4:]}",
                    "expiration": f"{card_data.get('expiration_month', 'XX')}/{card_data.get('expiration_year', 'XXXX')}",
                    "tokenized_at": card_data.get("tokenized_at", "N/A")
                },
                "warning": "Dados sensíveis mascarados para segurança"
            }
        else:
            safe_result = result
        
        return safe_result
        
    except Exception as e:
        logger.error(f"❌ Erro no teste de resolução: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no teste: {str(e)}")


# ========== EXPORTS ==========

__all__ = [
    "router",
    "InsertKeyRequest",
    "InsertKeyResponse", 
    "MigrationRequest",
    "BatchKeySetupRequest",
    "HealthCheckResponse",
]