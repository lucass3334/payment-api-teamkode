import httpx
import os
from ..utilities.logging_config import logger

BASE_URL = "https://www.asaas.com/api/v3"

async def create_asaas_payment(data: dict, api_key: str):
    """
    Cria um pagamento na API do Asaas.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/payments", json=data, headers=headers)
        if response.status_code != 200:
            logger.error(f"Erro ao criar pagamento no Asaas: {response.text}")
            raise Exception("Erro no Asaas")
        logger.info(f"Pagamento criado no Asaas: {response.json()}")
        return response.json()
