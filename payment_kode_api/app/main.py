import os
from fastapi import FastAPI
from payment_kode_api.app.routes import payments, webhooks
from payment_kode_api.app.config import settings
from payment_kode_api.app.error_handlers import add_error_handlers

app = FastAPI(
    title=settings.APP_NAME,
    version="0.0.1",
    description="API para gestão de pagamentos com fallback entre gateways",
    debug=settings.DEBUG,
)

# Inclui as rotas
app.include_router(payments.router, prefix="/payments", tags=["Pagamentos"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])

# Adiciona handlers de erro
add_error_handlers(app)

@app.get("/")
def health_check():
    """
    Verifica o status da aplicação.
    """
    return {"status": "OK", "message": "Payment Kode API funcionando!"}
