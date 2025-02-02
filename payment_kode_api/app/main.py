from fastapi import FastAPI
from payment_kode_api.app.routes import payments_router, webhooks_router, empresas_router  # ✅ Importação correta das rotas
from payment_kode_api.app.config import settings
from payment_kode_api.app.error_handlers import add_error_handlers
from payment_kode_api.app.utilities.logging_config import logger

def create_app() -> FastAPI:
    """
    Inicializa e retorna a aplicação FastAPI configurada.
    """
    debug_mode = settings.DEBUG if isinstance(settings.DEBUG, bool) else str(settings.DEBUG).lower() in ["true", "1"]  # 🔹 Corrige `DEBUG`

    app = FastAPI(
        title=settings.APP_NAME if hasattr(settings, "APP_NAME") else "Payment Kode API",
        version="0.0.1",
        description="API para gestão de pagamentos com fallback entre gateways",
        debug=debug_mode,  # ✅ Corrige possível erro de tipo
    )

    # Inclui as rotas
    app.include_router(payments_router, prefix="/payments", tags=["Pagamentos"])
    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(empresas_router, prefix="/empresas", tags=["Empresas"])  # ✅ Garante que rota de empresas está incluída

    # Adiciona handlers de erro
    add_error_handlers(app)

    @app.on_event("startup")
    async def startup_event():
        """
        Inicializa configurações necessárias no startup.
        """
        if not logger:
            from payment_kode_api.app.utilities.logging_config import logger  # 🔹 Garante que logger está carregado
        
        logger.info("🚀 Aplicação iniciando...")
        logger.info(f"✅ API `{app.title}` versão `{app.version}` inicializada com sucesso!")
        logger.info(f"🔧 Modo Debug: {'Ativado' if app.debug else 'Desativado'}")

    @app.get("/", tags=["Health Check"])
    async def health_check():
        """
        Verifica o status da aplicação.
        """
        return {"status": "OK", "message": "Payment Kode API funcionando!"}

    return app

# Instância global da aplicação para importação
app = create_app()

__all__ = ["app", "create_app"]
