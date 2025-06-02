# payment_kode_api/app/main.py

import os
from dotenv import load_dotenv; load_dotenv()  # 🔹 Carrega variáveis do .env

from fastapi import FastAPI, Response
from payment_kode_api.app.api.routes import (
    payments_router,
    webhooks_router,
    empresas_router,
    upload_certificados_router,    # ✅ Roteador de certificados
    auth_gateway_router,           # ✅ Roteador para tokens Sicredi
    refunds_router                 # ✅ Roteador de estornos
)
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.core.error_handlers import add_error_handlers
from payment_kode_api.app.utilities.logging_config import logger

# 🆕 NOVO: Import da rota de clientes
from payment_kode_api.app.api.routes.clientes import router as clientes_router

def create_app() -> FastAPI:
    debug_mode = settings.DEBUG if isinstance(settings.DEBUG, bool) else str(settings.DEBUG).lower() in ["true", "1"]

    app = FastAPI(
        title=getattr(settings, "APP_NAME", "Payment Kode API"),
        version="0.1.0",  # 🔧 Atualizada versão para refletir novas funcionalidades
        description="API para gestão de pagamentos com fallback entre gateways e gerenciamento completo de clientes com endereço",
        debug=debug_mode,
    )

    # 🔹 Rotas principais da API
    app.include_router(payments_router, prefix="/payments", tags=["Pagamentos"])
    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(empresas_router, prefix="/empresas", tags=["Empresas"])
    app.include_router(upload_certificados_router, tags=["Certificados"])
    app.include_router(auth_gateway_router, tags=["Autenticação"])
    app.include_router(refunds_router, prefix="/payments", tags=["Estornos"])
    
    # 🆕 NOVA: Rota de clientes com gestão completa
    app.include_router(clientes_router, prefix="/api/v1", tags=["Clientes"])

    # 🔹 Handlers de erro globais
    add_error_handlers(app)

    @app.on_event("startup")
    async def startup_event():
        logger.info("🚀 Aplicação iniciando...")
        logger.info("📦 Certificados Sicredi serão carregados dinamicamente da memória via Supabase Storage.")
        logger.info(f"✅ API `{app.title}` versão `{app.version}` inicializada!")
        logger.info(f"🔧 Debug: {'Ativado' if app.debug else 'Desativado'}")
        
        # 🆕 Log das novas funcionalidades
        logger.info("🆕 Nova funcionalidade: Gestão completa de clientes com endereço ativada!")
        logger.info("🔗 Rotas disponíveis:")
        logger.info("   - Pagamentos PIX/Cartão com criação automática de cliente")
        logger.info("   - Tokenização com dados completos do cliente")
        logger.info("   - CRUD completo de clientes e endereços")
        logger.info("   - Relacionamentos: pagamentos, cartões, estatísticas")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("🛑 Aplicação sendo encerrada...")

    @app.get("/", tags=["Health Check"])
    @app.head("/", tags=["Health Check"])
    async def health_check(response: Response):
        response.headers["Cache-Control"] = "no-cache"
        return {
            "status": "OK",
            "message": "Payment Kode API operacional",
            "version": "0.1.0",
            "features": [
                "Pagamentos PIX e Cartão de Crédito",
                "Fallback automático entre gateways (Sicredi, Rede, Asaas)",
                "Criação automática de clientes com endereço",
                "Tokenização segura de cartões",
                "Sistema completo de estornos",
                "Webhooks em tempo real",
                "Gestão completa de clientes e endereços",
                "Relacionamentos e estatísticas de clientes"
            ],
            "gateways": {
                "pix": ["sicredi", "asaas"],
                "credit_card": ["rede", "asaas"]
            },
            "endpoints": {
                "payments": "/payments",
                "clients": "/api/v1/clientes",
                "tokenization": "/tokenize-card",
                "refunds": "/payments/refund",
                "webhooks": "/webhooks",
                "companies": "/empresas",
                "certificates": "/certificados",
                "auth": "/auth_gateway"
            },
            "api_local": settings.API_LOCAL,
            "environment": {
                "use_sandbox": settings.USE_SANDBOX,
                "sicredi_env": getattr(settings, 'SICREDI_ENV', 'production'),
                "debug": debug_mode
            }
        }

    # 🆕 NOVO: Endpoint de documentação das funcionalidades de cliente
    @app.get("/api/v1/info", tags=["Documentação"])
    async def client_features_info():
        """
        Retorna informações sobre as funcionalidades de gestão de clientes.
        """
        return {
            "client_management": {
                "description": "Gestão completa de clientes com endereços separados",
                "features": [
                    "Criação automática durante pagamentos e tokenização",
                    "CRUD completo de clientes",
                    "Gestão de múltiplos endereços por cliente",
                    "Relacionamentos com pagamentos e cartões",
                    "Estatísticas e histórico de transações",
                    "Busca por UUID interno ou ID externo customizado"
                ]
            },
            "automatic_creation": {
                "description": "Cliente criado automaticamente quando dados suficientes fornecidos",
                "triggers": [
                    "Tokenização de cartão com dados do cliente",
                    "Pagamento PIX com dados do devedor",
                    "Pagamento cartão com dados do portador"
                ],
                "required_fields": {
                    "minimum": ["nome"],
                    "recommended": ["nome", "email", "cpf_cnpj"],
                    "complete": ["nome", "email", "cpf_cnpj", "telefone", "endereço_completo"]
                }
            },
            "search_priority": [
                "customer_external_id (se fornecido)",
                "cpf_cnpj (unique constraint)",
                "email (unique constraint)",
                "criar novo se não encontrar"
            ],
            "database_structure": {
                "clientes": "Dados básicos do cliente + customer_external_id",
                "enderecos": "Endereços separados com FK para clientes.id",
                "cartoes_tokenizados": "Referência customer_id (UUID) para clientes.id",
                "payments": "Nova coluna cliente_id (UUID) para clientes.id"
            }
        }

    return app

app = create_app()
__all__ = ["app", "create_app"]