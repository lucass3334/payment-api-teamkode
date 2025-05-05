# payment_kode_api/app/database/customers.py

from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from .supabase_client import supabase
from ..services.config_service import get_empresa_credentials  # traz as credenciais
from payment_kode_api.app.core.config import settings

async def get_asaas_customer(empresa_id: str, local_customer_id: str) -> Optional[str]:
    """
    Retorna o ID do cliente Asaas para uma empresa e identificador local, se existir.
    """
    resp = (
        supabase
        .table("asaas_customers")
        .select("asaas_customer_id")
        .eq("empresa_id", empresa_id)
        .eq("local_customer_id", local_customer_id)
        .limit(1)
        .execute()
    )
    return resp.data[0]["asaas_customer_id"] if resp.data else None

async def save_asaas_customer(
    empresa_id: str,
    local_customer_id: str,
    asaas_customer_id: str
) -> None:
    """
    Persiste um novo cliente Asaas vinculado à empresa e identificador local.
    """
    supabase.table("asaas_customers").insert({
        "empresa_id":        empresa_id,
        "local_customer_id": local_customer_id,
        "asaas_customer_id": asaas_customer_id,
        "created_at":        datetime.now(timezone.utc).isoformat()
    }).execute()

async def get_or_create_asaas_customer(
    empresa_id: str,
    local_customer_id: str,
    customer_data: dict
) -> str:
    """
    Retorna o ID Asaas de um cliente existente ou cria um novo se não existir.
    customer_data deve conter campos necessários para cadastro ("name", "email", etc.).
    """
    # 1) tenta obter cliente localmente
    existing = await get_asaas_customer(empresa_id, local_customer_id)
    if existing:
        return existing

    # 2) prepara chamada à API Asaas
    creds = await get_empresa_credentials(empresa_id)
    api_key = creds.get("asaas_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="Asaas API key não configurada para esta empresa.")

    use_sandbox = creds.get("use_sandbox", True)
    url = (
        "https://sandbox.asaas.com/api/v3/customers"
        if use_sandbox else
        "https://api.asaas.com/v3/customers"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json"
    }

    payload = {
        "name":              customer_data.get("name"),
        "email":             customer_data.get("email"),
        "cpfCnpj":           customer_data.get("cpfCnpj") or customer_data.get("cpf"),
        "phone":             customer_data.get("phone"),
        "mobilePhone":       customer_data.get("mobilePhone"),
        "postalCode":        customer_data.get("postalCode"),
        "address":           customer_data.get("address"),
        "addressNumber":     customer_data.get("addressNumber"),
        "externalReference": customer_data.get("externalReference", local_customer_id)
    }

    # 3) chama API Asaas para criar cliente
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao criar cliente Asaas")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Erro de conexão ao criar cliente Asaas")

    data = resp.json()
    new_id = data.get("id") or data.get("customerId")
    if not new_id:
        raise HTTPException(status_code=500, detail="Resposta inválida ao criar cliente Asaas")

    # 4) persiste no nosso banco e retorna
    await save_asaas_customer(empresa_id, local_customer_id, new_id)
    return new_id
