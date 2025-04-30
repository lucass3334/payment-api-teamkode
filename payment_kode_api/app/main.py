import os
from dotenv import load_dotenv; load_dotenv()  # 🔹 Carrega variáveis do .env

from fastapi import FastAPI, Response
from payment_kode_api.app.api.routes import (
    payments_router,
    webhooks_router,
    empresas_router,
    upload_certificados_router,    # ✅ Novo roteador
    auth_gateway_router,           # ✅ Novo roteador para tokens Sicredi
    refunds_router                 # ✅ Novo roteador de estornos
)
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.core.error_handlers import add_error_handlers
from payment_kode_api.app.utilities.logging_config import logger
# from redis import Redis  # ❌ Desativado

def create_app() -> FastAPI:
    debug_mode = settings.DEBUG if isinstance(settings.DEBUG, bool) else str(settings.DEBUG).lower() in ["true", "1"]

    app = FastAPI(
        title=getattr(settings, "APP_NAME", "Payment Kode API"),
        version="0.0.1",
        description="API para gestão de pagamentos com fallback entre gateways",
        debug=debug_mode,
    )

    # Rotas
    app.include_router(payments_router, prefix="/payments", tags=["Pagamentos"])
    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(empresas_router, prefix="/empresas", tags=["Empresas"])
    app.include_router(upload_certificados_router, tags=["Certificados"])      # Mantém sem prefixo adicional
    app.include_router(auth_gateway_router, tags=["Autenticação"])            # Mantém sem prefixo adicional
    app.include_router(refunds_router, prefix="/payments", tags=["Estornos"])  # Inclui rota de estorno

    # Handlers de erro
    add_error_handlers(app)

    @app.on_event("startup")
    async def startup_event():
        logger.info("🚀 Aplicação iniciando...")

        logger.info("📦 Certificados Sicredi serão carregados dinamicamente da memória via Supabase Storage.")

        # 🔴 Redis desativado
        # try:
        #     app.state.redis = Redis.from_url(
        #         settings.REDIS_URL,
        #         ssl=settings.REDIS_USE_SSL,
        #         ssl_cert_reqs=settings.REDIS_SSL_CERT_REQS,
        #         decode_responses=True
        #     )
        #     logger.success("✅ Redis conectado com sucesso!")
        # except Exception as e:
        #     logger.critical(f"❌ Falha crítica ao conectar com Redis: {str(e)}")
        #     raise

        logger.info(f"✅ API `{app.title}` versão `{app.version}` inicializada!")
        logger.info(f"🔧 Debug: {'Ativado' if app.debug else 'Desativado'}")

    @app.get("/", tags=["Health Check"])
    @app.head("/", tags=["Health Check"])
    async def health_check(response: Response):
        response.headers["Cache-Control"] = "no-cache"
        return {
            "status": "OK",
            "message": "Payment Kode API operacional",
            "api_local": settings.API_LOCAL  # ✅ Adicionado para refletir o estado da variável
        }

    return app

app = create_app()
__all__ = ["app", "create_app"]
