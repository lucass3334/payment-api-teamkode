from supabase import create_client
from app.config import settings
from app.utilities.logging_config import logger

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

def save_payment(data: dict):
    """
    Salva o pagamento no banco de dados.
    """
    try:
        response = supabase.table("payments").insert(data).execute()
        logger.info(f"Pagamento salvo no banco: {response}")
        return response
    except Exception as e:
        logger.error(f"Erro ao salvar pagamento: {e}")
        raise
