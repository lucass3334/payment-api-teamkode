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
    # ✅ NOVO: Dependency injection das interfaces
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """Cria uma nova empresa, gera suas chaves RSA e retorna o ID e access_token."""
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
        
        # ✅ USANDO INTERFACE: Salvar certificados
        await empresa_repo.save_empresa_certificados(
            empresa_id=empresa_id,
            sicredi_cert_base64=private_key,
            sicredi_key_base64=public_key,
            sicredi_ca_base64=None  
        )
        
        logger.info(f"✅ Empresa criada com sucesso: {empresa_id} - {empresa_data.nome}")
        return {"empresa_id": empresa_id, "access_token": access_token}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Erro ao criar empresa: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao criar empresa.")


@router.get("/empresa/token/{access_token}")
async def validate_access_token(
    access_token: str,
    # ✅ NOVO: Dependency injection da interface
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