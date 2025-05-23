# payment_kode_api/app/api/routes/__init__.py

from .payments import router as payments_router
from .webhooks import router as webhooks_router
from .empresas import router as empresas_router
from .tokenization import router as tokenization_router
from .upload_certificados import router as upload_certificados_router
from .auth_gateway import router as auth_gateway_router
from .refunds import router as refunds_router       # ✅ Novo roteador de estornos

__all__ = [
    "payments_router",
    "webhooks_router",
    "empresas_router",
    "tokenization_router",
    "upload_certificados_router",
    "auth_gateway_router",
    "refunds_router"                                # ✅ Exportado também
]

