from fastapi import FastAPI, APIRouter, Response
from payment_kode_api.app.routes import payments_router, webhooks_router, empresas_router
from payment_kode_api.app.config import settings
from payment_kode_api.app.error_handlers import add_error_handlers
from payment_kode_api.app.utilities.logging_config import logger
from redis import Redis

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

    # Handlers de erro
    add_error_handlers(app)

    @app.on_event("startup")
    async def startup_event():
        """Inicialização de recursos durante o startup"""
        logger.info("🚀 Aplicação iniciando...")
        
        try:
            app.state.redis = Redis.from_url(
                settings.REDIS_URL,
                ssl=settings.REDIS_USE_SSL,
                ssl_cert_reqs=settings.REDIS_SSL_CERT_REQS,
                decode_responses=True
            )
            logger.success("✅ Redis conectado com sucesso!")
        except Exception as e:
            logger.critical(f"❌ Falha crítica no Redis: {str(e)}")
            raise

        logger.info(f"✅ API `{app.title}` versão `{app.version}` inicializada!")
        logger.info(f"🔧 Debug: {'Ativado' if app.debug else 'Desativado'}")

    @app.get("/", tags=["Health Check"])
    @app.head("/", tags=["Health Check"])
    async def health_check(response: Response):
        """Endpoint para health check e monitoramento"""
        response.headers["Cache-Control"] = "no-cache"
        return {"status": "OK", "message": "Payment Kode API operacional"}

    return app

app = create_app()
__all__ = ["app", "create_app"]