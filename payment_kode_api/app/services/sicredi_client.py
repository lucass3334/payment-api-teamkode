import httpx
from ..utilities.logging_config import logger

BASE_URL = "https://api.sicredi.com.br/v1"

async def create_sicredi_payment(data: dict):
    """
    Cria um pagamento na API do Sicredi.
    """
    headers = {"Authorization": f"Bearer {data.get('SICREDI_API_KEY')}"}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/payments", json=data, headers=headers)
        if response.status_code != 200:
            logger.error(f"Erro ao criar pagamento no Sicredi: {response.text}")
            raise Exception("Erro no Sicredi")
        logger.info(f"Pagamento criado no Sicredi: {response.json()}")
        return response.json()
