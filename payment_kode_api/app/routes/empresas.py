from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic.types import StringConstraints
from typing import Annotated
from ..database.database import save_empresa, get_empresa
from ..utilities.logging_config import logger
import uuid

router = APIRouter()

# Tipagem de validação
EmpresaIDType = Annotated[str, StringConstraints(min_length=36, max_length=36)]  # UUID da empresa

class EmpresaRequest(BaseModel):
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]  # CNPJ sem formatação
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]
    telefone: Annotated[str, StringConstraints(min_length=10, max_length=15)]

class EmpresaResponse(BaseModel):
    empresa_id: str

@router.post("/empresa", response_model=EmpresaResponse)
async def create_empresa(empresa_data: EmpresaRequest):
    """Cria uma nova empresa se o CNPJ ainda não estiver cadastrado e retorna o ID gerado."""
    try:
        # Verifica se o CNPJ já existe
        existing_empresa = get_empresa(empresa_data.cnpj)
        if existing_empresa:
            logger.warning(f"Tentativa de criar empresa com CNPJ já existente: {empresa_data.cnpj}")
            raise HTTPException(status_code=400, detail="CNPJ já cadastrado para outra empresa.")

        empresa_id = str(uuid.uuid4())
        save_empresa({
            "empresa_id": empresa_id,
            "nome": empresa_data.nome,
            "cnpj": empresa_data.cnpj,
            "email": empresa_data.email,
            "telefone": empresa_data.telefone
        })
        logger.info(f"Empresa criada com sucesso: {empresa_id} - {empresa_data.nome}")

        return {"empresa_id": empresa_id}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erro ao criar empresa: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao criar empresa.")

@router.get("/empresa/{empresa_id}", response_model=EmpresaRequest)
async def get_empresa_info(empresa_id: EmpresaIDType):
    """Recupera informações de uma empresa pelo seu ID."""
    empresa = get_empresa(empresa_id)
    if not empresa:
        logger.warning(f"Tentativa de acessar empresa inexistente: {empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    logger.info(f"Empresa consultada: {empresa_id} - {empresa['nome']}")
    return empresa
