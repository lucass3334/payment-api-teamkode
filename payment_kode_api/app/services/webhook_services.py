import httpx
from payment_kode_api.app.utilities.logging_config import logger

USER_AGENT = "payment-kode-api/1.0 (env=production; system=FastAPI; contact=administrativo@teamkode.com)"

async def notify_user_webhook(webhook_url: str, data: dict) -> None:
    """
    Dispara uma notificação HTTP POST para o webhook definido pelo cliente,
    com o status atualizado de pagamento.

    Headers incluem identificação via User-Agent, útil para logging e segurança no servidor remoto.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(webhook_url, json=data, headers=headers)
            response.raise_for_status()
            logger.info(f"📤 Notificação enviada com sucesso para {webhook_url}")
    except httpx.RequestError as e:
        logger.warning(f"⚠️ Erro de conexão ao notificar {webhook_url}: {e}")
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"⚠️ Webhook {webhook_url} respondeu com erro HTTP {e.response.status_code}: {e.response.text}"
        )
