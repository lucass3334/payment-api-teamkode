import httpx
from payment_kode_api.app.utilities.logging_config import logger

async def notify_user_webhook(webhook_url: str, data: dict) -> None:
    """
    Dispara uma notificação para a URL de webhook definida pelo cliente.
    Utilizado para notificar status de pagamento atualizado.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(webhook_url, json=data)
            response.raise_for_status()
            logger.info(f"📤 Notificação enviada com sucesso para {webhook_url}")
    except httpx.RequestError as e:
        logger.warning(f"⚠️ Erro de conexão ao notificar {webhook_url}: {e}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"⚠️ Webhook {webhook_url} respondeu com erro HTTP: {e.response.status_code}")
