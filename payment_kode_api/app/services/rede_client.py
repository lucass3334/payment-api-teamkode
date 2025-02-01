import httpx
from app.utilities.logging_config import logger

BASE_URL = "https://api.userede.com.br"

async def create_rede_payment(data: dict):
    """
    Cria um pagamento na API do Rede.
    """
    headers = {"Authorization": f"Bearer {data.get('REDE_API_KEY')}"}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/payments", json=data, headers=headers)
        if response.status_code != 200:
            logger.error(f"Erro ao criar pagamento no Rede: {response.text}")
            raise Exception("Erro no Rede")
        logger.info(f"Pagamento criado no Rede: {response.json()}")
        return response.json()
