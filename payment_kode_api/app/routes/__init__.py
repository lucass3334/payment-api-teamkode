# Importação dos roteadores das rotas
from .payments import router as payments_router
from .webhooks import router as webhooks_router

# Define o que será exportado ao importar o módulo routes
__all__ = ["payments_router", "webhooks_router"]
