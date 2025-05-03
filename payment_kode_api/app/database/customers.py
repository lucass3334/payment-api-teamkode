# payment_kode_api/app/database/customers.py

from datetime import datetime, timezone
from typing import Optional
from .supabase_client import supabase

async def get_asaas_customer(empresa_id: str, local_customer_id: str) -> Optional[str]:
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
    supabase.table("asaas_customers").insert({
        "empresa_id":        empresa_id,
        "local_customer_id": local_customer_id,
        "asaas_customer_id": asaas_customer_id,
        "created_at":        datetime.now(timezone.utc).isoformat()
    }).execute()
