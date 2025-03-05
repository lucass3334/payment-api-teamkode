from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import uuid


from payment_kode_api.app.database.database import (
    save_tokenized_card, get_tokenized_card, delete_tokenized_card
)
from payment_kode_api.app.security.crypto import encrypt_card_data
from payment_kode_api.app.security.auth import validate_access_token

router = APIRouter()

class TokenizeCardRequest(BaseModel):
    """Requisição para tokenizar um cartão de crédito."""
    card_number: str
    expiration_month: str
    expiration_year: str
    security_code: str
    cardholder_name: str
    customer_id: str

class TokenizedCardResponse(BaseModel):
    """Resposta contendo o token do cartão armazenado."""
    card_token: str

@router.post("/tokenize-card", response_model=TokenizedCardResponse)
async def tokenize_card(
    card_data: TokenizeCardRequest,
    empresa: dict = Depends(validate_access_token)
):
    """Tokeniza um cartão dentro da API para uso seguro em pagamentos futuros."""
    empresa_id = empresa["empresa_id"]
    card_token = str(uuid.uuid4())  # Gera um token único

    encrypted_card = encrypt_card_data(empresa_id, card_data.dict())

    await save_tokenized_card({
        "empresa_id": empresa_id,
        "customer_id": card_data.customer_id,
        "card_token": card_token,
        "encrypted_card_data": encrypted_card
    })

    return {"card_token": card_token}

@router.get("/tokenize-card/{card_token}")
async def get_tokenized_card_route(
    card_token: str, empresa: dict = Depends(validate_access_token)
):
    """Recupera os dados de um cartão tokenizado (somente para uso interno)."""
    empresa_id = empresa["empresa_id"]
    card = await get_tokenized_card(card_token)
    
    if not card or card["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Token de cartão inválido ou não encontrado.")

    return card

@router.delete("/tokenize-card/{card_token}")
async def delete_tokenized_card_route(
    card_token: str, empresa: dict = Depends(validate_access_token)
):
    """Permite que um cliente remova um cartão tokenizado do sistema."""
    empresa_id = empresa["empresa_id"]
    card = await get_tokenized_card(card_token)
    
    # Verifica se o cartão existe antes de tentar deletar
    if not card:
        raise HTTPException(
            status_code=404,
            detail="Cartão não encontrado"
        )

    # Verifica se o cartão pertence à empresa correta
    if card["empresa_id"] != empresa_id:
        raise HTTPException(
            status_code=403, 
            detail="Não autorizado a deletar este cartão"
        )

    await delete_tokenized_card(card_token)
    
    return {"message": f"Cartão tokenizado {card_token} removido com sucesso"}


