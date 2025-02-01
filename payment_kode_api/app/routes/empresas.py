from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic.types import StringConstraints
from typing import Annotated
from ..database.database import save_empresa, get_empresa

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
    """Cria uma nova empresa e retorna o ID gerado."""
    empresa_id = str(uuid.uuid4())

    try:
        save_empresa({
            "empresa_id": empresa_id,
            "nome": empresa_data.nome,
            "cnpj": empresa_data.cnpj,
            "email": empresa_data.email,
            "telefone": empresa_data.telefone
        })
        return {"empresa_id": empresa_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar empresa: {str(e)}")


@router.get("/empresa/{empresa_id}", response_model=EmpresaRequest)
async def get_empresa_info(empresa_id: EmpresaIDType):
    """Recupera informações de uma empresa pelo seu ID."""
    empresa = get_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return empresa
