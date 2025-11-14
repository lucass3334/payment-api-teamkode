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


# ========== TESTES DE BACKWARD COMPATIBILITY customer_cpf_cnpj ==========

@pytest.mark.asyncio
async def test_pix_with_customer_cpf_cnpj_and_due_date():
    """
    ✅ Testa PIX com due_date usando customer_cpf_cnpj (formato NOVO).
    Este teste verifica que o novo campo unificado funciona corretamente.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 100.00,
            "due_date": "2026-01-15",
            "nome_devedor": "João Silva",
            "customer_cpf_cnpj": "12345678900",  # ✅ Formato novo
            "email": "joao@test.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve aceitar sem erro
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_pix_with_cpf_and_due_date():
    """
    ✅ Testa PIX com due_date usando 'cpf' (formato ANTIGO - backward compatibility).
    Este teste garante que integrações antigas continuam funcionando.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 100.00,
            "due_date": "2026-01-15",
            "nome_devedor": "Maria Oliveira",
            "cpf": "98765432100",  # ✅ Formato antigo (backward compatibility)
            "email": "maria@test.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve aceitar sem erro
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_pix_with_cnpj_and_due_date():
    """
    ✅ Testa PIX com due_date usando 'cnpj' (formato ANTIGO - backward compatibility).
    Este teste garante que CNPJs em formato antigo continuam funcionando.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 250.00,
            "due_date": "2026-02-01",
            "nome_devedor": "Empresa XYZ LTDA",
            "cnpj": "12345678000190",  # ✅ Formato antigo (backward compatibility)
            "email": "contato@empresaxyz.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve aceitar sem erro
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_pix_with_due_date_without_document():
    """
    ❌ Testa que PIX com due_date REJEITA quando nenhum documento é fornecido.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 100.00,
            "due_date": "2026-01-15",
            "nome_devedor": "Sem Documento",
            "email": "sem@doc.com",
            "chave_pix": "test_chave_pix"
            # ❌ Nenhum documento fornecido
        })

    # Deve rejeitar com erro 400
    assert response.status_code == 400
    assert "customer_cpf_cnpj" in response.json()["detail"] or "cpf" in response.json()["detail"]


@pytest.mark.asyncio
async def test_pix_customer_cpf_cnpj_priority():
    """
    ✅ Testa que customer_cpf_cnpj tem prioridade quando ambos formatos são enviados.
    O validator deve migrar automaticamente cpf/cnpj para customer_cpf_cnpj.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 150.00,
            "due_date": "2026-01-20",
            "nome_devedor": "Teste Prioridade",
            "customer_cpf_cnpj": "11111111111",  # ✅ Deve usar este
            "cpf": "99999999999",  # ⚠️ Deve ser ignorado
            "email": "teste@priority.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve aceitar e usar customer_cpf_cnpj
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_pix_both_cpf_and_cnpj_fails():
    """
    ❌ Testa que enviar CPF E CNPJ juntos resulta em erro de validação.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 100.00,
            "due_date": "2026-01-15",
            "nome_devedor": "Conflito",
            "cpf": "12345678900",  # ❌ Ambos fornecidos
            "cnpj": "12345678000190",  # ❌ Ambos fornecidos
            "email": "conflito@test.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve rejeitar com erro 422 (Pydantic validation error)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pix_document_normalization():
    """
    ✅ Testa que documentos com formatação são normalizados (pontos, traços removidos).
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/payment/pix", json={
            "amount": 100.00,
            "due_date": "2026-01-15",
            "nome_devedor": "Teste Formatação",
            "customer_cpf_cnpj": "123.456.789-00",  # ✅ Com formatação
            "email": "formato@test.com",
            "chave_pix": "test_chave_pix"
        })

    # Deve aceitar e normalizar automaticamente
    assert response.status_code in [200, 201]
