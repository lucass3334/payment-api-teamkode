# payment_kode_api/app/database/customers.py

from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from .supabase_client import supabase
from payment_kode_api.app.services.gateways.asaas_client import get_asaas_headers


async def get_asaas_customer(empresa_id: str, local_customer_id: str) -> Optional[str]:
    """
    Retorna o ID do cliente Asaas já cadastrado para uma empresa e identificador local, se existir.
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
    if resp.data:
        return resp.data[0]["asaas_customer_id"]
    return None


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
    customer_data deve conter os campos necessários: "name", "email", "cpfCnpj", etc.
    """
    # 1) Tenta obter cliente já cadastrado no nosso banco
    existing = await get_asaas_customer(empresa_id, local_customer_id)
    if existing:
        return existing

    # 2) Cabeçalhos e URL
    headers = await get_asaas_headers(empresa_id)
    use_sandbox = headers.pop("use_sandbox", False)  # se você tiver armazenado essa flag nos headers
    base_url = (
        "https://sandbox.asaas.com/api/v3/customers"
        if use_sandbox else
        "https://api.asaas.com/v3/customers"
    )

    payload = {
        "name":              customer_data.get("name"),
        "email":             customer_data.get("email"),
        "cpfCnpj":           customer_data.get("cpfCnpj") or customer_data.get("cpf"),
        "phone":             customer_data.get("phone"),
        "mobilePhone":       customer_data.get("mobilePhone"),
        "postalCode":        customer_data.get("postalCode"),
        "address":           customer_data.get("address"),
        "addressNumber":     customer_data.get("addressNumber"),
        "externalReference": customer_data.get("externalReference")
    }

    # 3) Cria o cliente na API Asaas
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(base_url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail="Erro ao criar cliente no Asaas"
            )
        except Exception as e:
            raise HTTPException(500, "Erro inesperado ao criar cliente no Asaas")

    data = resp.json()
    new_id = data.get("id") or data.get("customerId")
    if not new_id:
        raise HTTPException(500, "Resposta inválida ao criar cliente no Asaas")

    # 4) Salva no nosso banco para uso futuro
    await save_asaas_customer(empresa_id, local_customer_id, new_id)
    return new_id


__all__ = [
    "get_asaas_customer",
    "save_asaas_customer",
    "get_or_create_asaas_customer",
]
