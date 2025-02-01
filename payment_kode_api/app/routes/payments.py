from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..services.asaas_client import create_asaas_payment
from ..services.sicredi_client import create_sicredi_payment
from ..services.rede_client import create_rede_payment

router = APIRouter()

@router.post("/create")
async def create_payment(payment_data: dict, background_tasks: BackgroundTasks):
    """
    Endpoint para criar um pagamento.
    O pagamento será processado em segundo plano com fallback para o gateway disponível.
    """
    try:
        # Adiciona a tarefa em background
        background_tasks.add_task(create_sicredi_payment, payment_data)
        return {"status": "processing", "message": "Pagamento sendo processado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
