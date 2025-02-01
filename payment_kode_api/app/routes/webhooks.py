from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.post("/asaas")
async def handle_asaas_webhook(request: Request):
    """
    Webhook para receber notificações do Asaas.
    """
    payload = await request.json()
    # Processa o payload
    return {"status": "received", "payload": payload}

@router.post("/rede")
async def handle_rede_webhook(request: Request):
    """
    Webhook para receber notificações do Rede.
    """
    payload = await request.json()
    return {"status": "received", "payload": payload}
