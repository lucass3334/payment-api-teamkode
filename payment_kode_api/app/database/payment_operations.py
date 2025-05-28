# payment_operations.py
### Não usado


from payment_kode_api.app.utilities.logging_config import logger
from payment_kode_api.app.database.supabase_client import supabase  # ✅ Corrigido aqui
from datetime import datetime, timezone

VALID_PAYMENT_STATUSES = {"pending", "approved", "failed", "canceled"}

async def update_payment_status(transaction_id: str, empresa_id: str, status: str):
    if status not in VALID_PAYMENT_STATUSES:
        raise ValueError(f"Status inválido: {status}")

    update_data = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    response = (
        supabase.table("payments")
        .update(update_data)
        .eq("transaction_id", transaction_id)
        .eq("empresa_id", empresa_id)
        .execute()
    )

    if not response.data:
        logger.warning(f"⚠️ Pagamento não encontrado: Empresa {empresa_id}, transaction_id {transaction_id}")
        return None

    logger.info(f"✅ Status atualizado: Empresa {empresa_id}, transaction_id {transaction_id} → {status}")
    return response.data[0]
