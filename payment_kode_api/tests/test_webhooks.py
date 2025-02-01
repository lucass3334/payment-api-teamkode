import pytest
from httpx import AsyncClient
from payment_kode_api.app.main import app

@pytest.mark.asyncio
async def test_webhook_pix_success():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/webhooks/pix", json={
            "transaction_id": "1234567890",
            "status": "APPROVED"
        })
    
    assert response.status_code == 200
    assert response.json()["message"] == "Webhook processado com sucesso"

@pytest.mark.asyncio
async def test_webhook_pix_failed():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/webhooks/pix", json={
            "transaction_id": "0987654321",
            "status": "FAILED"
        })
    
    assert response.status_code == 400
    assert response.json()["message"] == "Erro ao processar webhook"

@pytest.mark.asyncio
async def test_webhook_pix_invalid_payload():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/webhooks/pix", json={
            "transaction_id": "",
            "status": "UNKNOWN"
        })
    
    assert response.status_code == 400
    assert "message" in response.json()

@pytest.mark.asyncio
async def test_webhook_pix_missing_fields():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/webhooks/pix", json={})
    
    assert response.status_code == 422
