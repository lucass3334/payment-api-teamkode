import pytest
from httpx import AsyncClient
from payment_kode_api.app.main import app

@pytest.mark.asyncio
async def test_create_pix_payment():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payments/pix", json={
            "amount": 100.50,
            "chave_pix": "test_chave_pix",
            "txid": "1234567890"
        })
    
    assert response.status_code == 200
    assert response.json()["status"] == "processing"

@pytest.mark.asyncio
async def test_create_credit_card_payment():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payments/credit-card", json={
            "amount": 250.75,
            "transaction_id": "987654321",
            "card_data": {
                "cardholder_name": "John Doe",
                "card_number": "4111111111111111",
                "expiration_month": "12",
                "expiration_year": "2026",
                "security_code": "123"
            }
        })
    
    assert response.status_code == 200
    assert response.json()["status"] == "processing"

@pytest.mark.asyncio
async def test_create_payment_invalid_type():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payments/credit-card", json={
            "amount": 150.00,
            "transaction_id": "123456",
            "card_data": None
        })
    
    assert response.status_code == 400
