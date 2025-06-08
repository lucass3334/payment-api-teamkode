# payment_kode_api/app/api/routes/empresas.py
# -*- coding: utf-8 -*- 

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pydantic.types import StringConstraints
from typing import Annotated

# ✅ NOVO: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    EmpresaRepositoryInterface,
    CertificateServiceInterface,
)

# ✅ NOVO: Dependency injection
from ...dependencies import (
    get_empresa_repository,
    get_certificate_service,
)

# 🆕 NOVO: Import do serviço de criptografia por empresa
from ...services.company_encryption import CompanyEncryptionService

from ...utilities.logging_config import logger
import uuid
import secrets
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import base64

# Imports para configuração de gateways (mantido igual)
from ...models import EmpresaGatewayConfigSchema
from ...database.database import (atualizar_config_gateway, get_empresa_gateways)

router = APIRouter()

# Tipagem de validação (mantida igual)
EmpresaIDType = Annotated[str, StringConstraints(min_length=36, max_length=36)]

class EmpresaRequest(BaseModel):
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]
    telefone: Annotated[str, StringConstraints(min_length=10, max_length=15)]

class EmpresaResponse(BaseModel):
    empresa_id: str
    access_token: str
    # 🆕 NOVO: Informação sobre criptografia
    encryption_configured: bool = True
    encryption_method: str = "company_key_v1"


def generate_rsa_keys():
    """Gera um par de chaves RSA e retorna como strings Base64."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return base64.b64encode(private_pem).decode(), base64.b64encode(public_pem).decode()


@router.post("/empresa", response_model=EmpresaResponse)
async def create_empresa(
    empresa_data: EmpresaRequest,
    # ✅ MANTIDO: Dependency injection das interfaces
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """
    🔧 ATUALIZADO: Cria uma nova empresa, gera suas chaves RSA E chave de criptografia única.
    Agora inclui sistema de criptografia por empresa para tokenização segura.
    """
    try:
        # ✅ USANDO INTERFACE: Verificar se CNPJ já está cadastrado
        logger.info(f"🔍 Verificando se CNPJ já está cadastrado: {empresa_data.cnpj}")
        
        existing_empresa = await empresa_repo.get_empresa(empresa_data.cnpj)
        logger.info(f"🔍 Resultado da consulta para CNPJ ({empresa_data.cnpj}): {existing_empresa}")

        if existing_empresa:
            logger.warning(f"🚨 Tentativa de criar empresa com CNPJ já existente: {empresa_data.cnpj}")
            raise HTTPException(status_code=400, detail="CNPJ já cadastrado para outra empresa.")

        empresa_id = str(uuid.uuid4())
        access_token = secrets.token_urlsafe(32)
        private_key, public_key = generate_rsa_keys()
        
        # ✅ USANDO INTERFACE: Salvar empresa
        await empresa_repo.save_empresa({
            "empresa_id": empresa_id,
            "nome": empresa_data.nome,
            "cnpj": empresa_data.cnpj,
            "email": empresa_data.email,
            "telefone": empresa_data.telefone,
            "access_token": access_token
        })
        
        # ✅ USANDO INTERFACE: Salvar certificados RSA (mantido para compatibilidade)
        await empresa_repo.save_empresa_certificados(
            empresa_id=empresa_id,
            sicredi_cert_base64=private_key,
            sicredi_key_base64=public_key,
            sicredi_ca_base64=None  
        )
        
        # 🆕 NOVO: Configurar criptografia por empresa
        encryption_service = CompanyEncryptionService()
        encryption_configured = False
        encryption_method = "company_key_v1"
        
        try:
            # Gerar chave única para a empresa
            company_key = encryption_service.generate_company_decryption_key(empresa_id)
            
            # Salvar chave no banco
            await encryption_service.save_empresa_decryption_key(empresa_id, company_key)
            
            encryption_configured = True
            logger.info(f"🔐 Chave de criptografia gerada e salva para empresa {empresa_id}")
            
            # 🆕 NOVO: Verificar saúde da criptografia
            health_check = await encryption_service.verify_company_encryption_health(empresa_id)
            if health_check.get("status") != "healthy":
                logger.warning(f"⚠️ Problemas na configuração de criptografia: {health_check.get('issues', [])}")
            
        except Exception as encryption_error:
            logger.error(f"❌ Erro ao configurar criptografia para empresa {empresa_id}: {encryption_error}")
            # Não falha a criação da empresa, apenas registra o erro
            encryption_configured = False
        
        logger.info(f"✅ Empresa criada com sucesso: {empresa_id} - {empresa_data.nome}")
        logger.info(f"🔐 Criptografia configurada: {encryption_configured}")
        
        return EmpresaResponse(
            empresa_id=empresa_id, 
            access_token=access_token,
            encryption_configured=encryption_configured,
            encryption_method=encryption_method
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Erro ao criar empresa: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao criar empresa.")


@router.get("/empresa/token/{access_token}")
async def validate_access_token(
    access_token: str,
    # ✅ MANTIDO: Dependency injection da interface
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """Valida um access_token e retorna os dados da empresa associada."""
    try:
        # ✅ USANDO INTERFACE
        empresa = await empresa_repo.get_empresa_by_token(access_token)

        if not empresa:
            logger.warning(f"⚠️ Tentativa de acesso com token inválido: {access_token}")
            raise HTTPException(status_code=401, detail="Token inválido ou expirado.")
        
        logger.info(f"🔑 Access token validado com sucesso para empresa: {empresa['empresa_id']}")
        return empresa

    except Exception as e:
        logger.error(f"❌ Erro ao validar token: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao validar token.")


# 🆕 NOVO: Endpoint para verificar status da criptografia
@router.get("/empresa/{empresa_id}/encryption-status")
async def get_empresa_encryption_status(
    empresa_id: str,
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """
    🆕 NOVO: Verifica o status da criptografia de uma empresa.
    Útil para debugging e monitoramento.
    """
    try:
        # Verificar se empresa existe
        empresa = await empresa_repo.get_empresa_by_token(None)  # Usar endpoint interno se disponível
        # Alternativamente, fazer verificação direta:
        from ...database.supabase_client import supabase
        empresa_check = supabase.table("empresas").select("empresa_id").eq("empresa_id", empresa_id).execute()
        
        if not empresa_check.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        
        # Verificar status da criptografia
        encryption_service = CompanyEncryptionService()
        health_status = await encryption_service.verify_company_encryption_health(empresa_id)
        
        return {
            "empresa_id": empresa_id,
            "encryption_status": health_status,
            "timestamp": health_status.get("last_check")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao verificar status de criptografia: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao verificar criptografia.")


# 🆕 NOVO: Endpoint para migrar tokens RSA para novo sistema
@router.post("/empresa/{empresa_id}/migrate-tokens")
async def migrate_empresa_tokens(
    empresa_id: str,
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """
    🆕 NOVO: Migra tokens RSA existentes para o novo sistema de criptografia por empresa.
    Deve ser usado apenas uma vez após a atualização.
    """
    try:
        # Verificar se empresa existe
        from ...database.supabase_client import supabase
        empresa_check = supabase.table("empresas").select("empresa_id").eq("empresa_id", empresa_id).execute()
        
        if not empresa_check.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        
        # Executar migração
        encryption_service = CompanyEncryptionService()
        migration_stats = await encryption_service.migrate_rsa_tokens_to_company_encryption(empresa_id)
        
        logger.info(f"🔄 Migração de tokens concluída para empresa {empresa_id}: {migration_stats}")
        
        return {
            "empresa_id": empresa_id,
            "migration_completed": True,
            "stats": migration_stats,
            "message": f"Migração concluída. {migration_stats['migrated']} tokens migrados com sucesso."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na migração de tokens: {e}")
        raise HTTPException(status_code=500, detail="Erro interno na migração de tokens.")


# 🆕 NOVO: Endpoint para regenerar chave de criptografia
@router.post("/empresa/{empresa_id}/regenerate-encryption-key")
async def regenerate_empresa_encryption_key(
    empresa_id: str,
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """
    🆕 NOVO: Regenera chave de criptografia da empresa.
    
    ⚠️ ATENÇÃO: Isso invalidará todos os tokens existentes!
    Use apenas em casos de emergência ou comprometimento de segurança.
    """
    try:
        # Verificar se empresa existe
        from ...database.supabase_client import supabase
        empresa_check = supabase.table("empresas").select("empresa_id").eq("empresa_id", empresa_id).execute()
        
        if not empresa_check.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        
        # Contar tokens existentes (alerta)
        tokens_response = supabase.table("cartoes_tokenizados").select("card_token", count="exact").eq("empresa_id", empresa_id).execute()
        existing_tokens = tokens_response.count or 0
        
        if existing_tokens > 0:
            logger.warning(f"⚠️ REGENERAÇÃO DE CHAVE: {existing_tokens} tokens serão invalidados para empresa {empresa_id}")
        
        # Regenerar chave
        encryption_service = CompanyEncryptionService()
        new_key = encryption_service.generate_company_decryption_key(empresa_id)
        await encryption_service.save_empresa_decryption_key(empresa_id, new_key)
        
        # Verificar saúde
        health_status = await encryption_service.verify_company_encryption_health(empresa_id)
        
        logger.info(f"🔐 Nova chave de criptografia gerada para empresa {empresa_id}")
        
        return {
            "empresa_id": empresa_id,
            "key_regenerated": True,
            "warning": f"{existing_tokens} tokens existentes foram invalidados",
            "new_encryption_status": health_status,
            "message": "Chave regenerada com sucesso. Tokens antigos não funcionarão mais."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao regenerar chave: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao regenerar chave.")


@router.post("/empresa/configurar_gateway")
async def configurar_gateway(schema: EmpresaGatewayConfigSchema):
    """
    Atualiza os gateways padrão (Pix e Crédito) da empresa.
    📝 NOTA: Mantido sem migração pois usa funções específicas de config
    """
    try:
        atualizado = await atualizar_config_gateway(schema.model_dump())

        if not atualizado:
            raise HTTPException(status_code=404, detail="Empresa não encontrada ou configuração não atualizada.")

        logger.info(f"✅ Gateways configurados com sucesso para empresa {schema.empresa_id}")
        return {"status": "success", "message": "Gateways atualizados com sucesso."}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Erro ao configurar gateways da empresa {schema.empresa_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao configurar gateways.")


@router.get("/empresa/gateways/{empresa_id}")
async def obter_gateways_empresa(empresa_id: str):
    """
    Retorna os providers configurados (Pix e Crédito) para a empresa.
    📝 NOTA: Mantido sem migração pois usa funções específicas de config
    """
    try:
        gateways = await get_empresa_gateways(empresa_id)

        if not gateways:
            raise HTTPException(status_code=404, detail="Empresa não encontrada ou gateways não configurados.")

        logger.info(f"📦 Providers retornados para empresa {empresa_id}: {gateways}")
        return {"empresa_id": empresa_id, "gateways": gateways}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Erro ao obter gateways da empresa {empresa_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao consultar gateways.")


# 🆕 NOVO: Endpoint de health check para criptografia de todas as empresas
@router.get("/empresas/encryption-health")
async def get_all_empresas_encryption_health():
    """
    🆕 NOVO: Verifica saúde da criptografia de todas as empresas.
    Útil para monitoramento global do sistema.
    """
    try:
        from ...database.supabase_client import supabase
        
        # Buscar todas as empresas
        empresas_response = supabase.table("empresas").select("empresa_id, nome").execute()
        empresas = empresas_response.data or []
        
        encryption_service = CompanyEncryptionService()
        health_results = []
        
        for empresa in empresas:
            empresa_id = empresa["empresa_id"]
            try:
                health = await encryption_service.verify_company_encryption_health(empresa_id)
                health["empresa_nome"] = empresa["nome"]
                health_results.append(health)
            except Exception as e:
                health_results.append({
                    "empresa_id": empresa_id,
                    "empresa_nome": empresa["nome"],
                    "status": "error",
                    "error": str(e)
                })
        
        # Estatísticas gerais
        total_empresas = len(health_results)
        healthy = len([h for h in health_results if h.get("status") == "healthy"])
        warning = len([h for h in health_results if h.get("status") == "warning"])
        error = len([h for h in health_results if h.get("status") == "error"])
        
        return {
            "summary": {
                "total_empresas": total_empresas,
                "healthy": healthy,
                "warning": warning,
                "error": error,
                "health_percentage": round((healthy / total_empresas * 100), 1) if total_empresas > 0 else 0
            },
            "empresas": health_results,
            "timestamp": health_results[0].get("last_check") if health_results else None
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao verificar saúde geral: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao verificar saúde da criptografia.")