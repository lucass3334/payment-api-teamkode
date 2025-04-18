# Importação dos roteadores das rotas
from .payments import router as payments_router
from .webhooks import router as webhooks_router
from .empresas import router as empresas_router
from .tokenization import router as tokenization_router
from .upload_certificados import router as upload_certificados_router  # ✅ Novo roteador

# Define o que será exportado ao importar o módulo routes
__all__ = [
    "payments_router",
    "webhooks_router",
    "empresas_router",
    "tokenization_router",
    "upload_certificados_router"  # ✅ Adicionado à lista de exportação
]
