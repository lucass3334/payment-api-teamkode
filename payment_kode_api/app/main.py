# payment_kode_api/app/main.py

import os
from dotenv import load_dotenv; load_dotenv()

from fastapi import FastAPI, Response
from payment_kode_api.app.api.routes import (
    payments_router,
    webhooks_router,
    empresas_router,
    tokenization_router,
    upload_certificados_router,
    auth_gateway_router,
    refunds_router,
    clientes_router  # ✅ Agora disponível
)
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.core.error_handlers import add_error_handlers
from payment_kode_api.app.utilities.logging_config import logger

def create_app() -> FastAPI:
    debug_mode = settings.DEBUG if isinstance(settings.DEBUG, bool) else str(settings.DEBUG).lower() in ["true", "1"]

    app = FastAPI(
        title=getattr(settings, "APP_NAME", "Payment Kode API"),
        version="0.2.0",  # ✅ Versão atualizada
        description="API para gestão de pagamentos com fallback entre gateways, gestão completa de clientes, tokenização e parcelas validadas",
        debug=debug_mode,
    )

    # ========== ROTAS PRINCIPAIS ==========
    app.include_router(payments_router, prefix="/payments", tags=["Pagamentos"])
    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(empresas_router, prefix="/empresas", tags=["Empresas"])
    app.include_router(tokenization_router, prefix="/tokenization", tags=["Tokenização"])
    app.include_router(upload_certificados_router, tags=["Certificados"])
    app.include_router(auth_gateway_router, tags=["Autenticação"])
    app.include_router(refunds_router, prefix="/payments", tags=["Estornos"])
    
    # ✅ NOVA: Rota de clientes com gestão completa
    app.include_router(clientes_router, prefix="/api/v1", tags=["Clientes"])

    # ========== HANDLERS DE ERRO ==========
    add_error_handlers(app)

    @app.on_event("startup")
    async def startup_event():
        logger.info("🚀 Aplicação iniciando...")
        logger.info("📦 Certificados Sicredi serão carregados dinamicamente da memória via Supabase Storage.")
        logger.info(f"✅ API `{app.title}` versão `{app.version}` inicializada!")
        logger.info(f"🔧 Debug: {'Ativado' if app.debug else 'Desativado'}")
        
        # ✅ Log das funcionalidades corrigidas
        logger.info("🔧 Funcionalidades corrigidas ativadas:")
        logger.info("   - Tokenização com customer_id OPCIONAL e criação automática")
        logger.info("   - Validação inteligente de parcelas por gateway")
        logger.info("   - CRUD completo de clientes com endpoints")
        logger.info("   - Relacionamentos: pagamentos, cartões, estatísticas")
        logger.info("   - Validação de valor mínimo por parcela")

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
            "version": "0.2.0",
            "features": [
                "Pagamentos PIX e Cartão de Crédito",
                "Fallback automático entre gateways (Sicredi, Rede, Asaas)",
                "Tokenização com customer_id OPCIONAL",
                "Criação automática de clientes",
                "Validação inteligente de parcelas",
                "CRUD completo de clientes",
                "Sistema completo de estornos",
                "Webhooks em tempo real",
                "Gestão de endereços",
                "Estatísticas e relacionamentos"
            ],
            "gateways": {
                "pix": ["sicredi", "asaas"],
                "credit_card": ["rede", "asaas"]
            },
            "installments": {
                "max_installments": 12,
                "rede_min_per_installment": "5.00",
                "asaas_min_per_installment": "3.00",
                "validation": "automatic"
            },
            "client_management": {
                "optional_customer_id": True,
                "automatic_creation": True,
                "address_support": True,
                "payment_linking": True
            },
            "endpoints": {
                "payments": "/payments",
                "clients": "/api/v1/clientes",
                "tokenization": "/tokenization",
                "refunds": "/payments/refund",
                "webhooks": "/webhooks",
                "companies": "/empresas",
                "certificates": "/certificados",
                "auth": "/auth_gateway",
                "installments_validation": "/payments/validate-installments"
            },
            "api_local": settings.API_LOCAL,
            "environment": {
                "use_sandbox": settings.USE_SANDBOX,
                "sicredi_env": getattr(settings, 'SICREDI_ENV', 'production'),
                "debug": debug_mode
            }
        }

    # ✅ NOVO: Endpoint de documentação das funcionalidades corrigidas
    @app.get("/api/v1/info", tags=["Documentação"])
    async def client_features_info():
        """
        Retorna informações sobre as funcionalidades corrigidas e melhoradas.
        """
        return {
            "tokenization_improvements": {
                "description": "Tokenização com customer_id opcional e criação automática",
                "features": [
                    "customer_id é completamente opcional",
                    "Criação automática de cliente se dados fornecidos",
                    "Tokenização funciona com ou sem cliente",
                    "Relacionamento opcional com tabela clientes",
                    "Dados de endereço opcionais"
                ],
                "behavior": {
                    "with_customer_data": "Cria/busca cliente automaticamente",
                    "without_customer_data": "Tokeniza apenas o cartão",
                    "partial_data": "Usa dados disponíveis, nome do portador como fallback"
                }
            },
            "installments_validation": {
                "description": "Validação inteligente de parcelas por gateway",
                "rules": {
                    "rede": {
                        "max_installments": 12,
                        "min_amount_per_installment": "5.00",
                        "auto_adjustment": True
                    },
                    "asaas": {
                        "max_installments": 12,
                        "min_amount_per_installment": "3.00",
                        "auto_adjustment": True
                    }
                },
                "features": [
                    "Validação automática antes do pagamento",
                    "Ajuste inteligente do número de parcelas",
                    "Endpoint para pré-validação",
                    "Logs detalhados de ajustes"
                ]
            },
            "client_management": {
                "description": "CRUD completo de clientes com relacionamentos",
                "endpoints": {
                    "create": "POST /api/v1/clientes",
                    "list": "GET /api/v1/clientes",
                    "get": "GET /api/v1/clientes/{external_id}",
                    "update": "PUT /api/v1/clientes/{external_id}",
                    "delete": "DELETE /api/v1/clientes/{external_id}",
                    "payments": "GET /api/v1/clientes/{external_id}/pagamentos",
                    "cards": "GET /api/v1/clientes/{external_id}/cartoes",
                    "stats": "GET /api/v1/clientes/{external_id}/estatisticas",
                    "addresses": "GET /api/v1/clientes/{external_id}/enderecos"
                },
                "features": [
                    "ID externo customizável",
                    "Busca e paginação",
                    "Gestão de endereços",
                    "Relacionamentos com pagamentos e cartões",
                    "Estatísticas detalhadas"
                ]
            },
            "automatic_creation": {
                "description": "Criação automática durante pagamentos e tokenização",
                "triggers": [
                    "Tokenização com dados do cliente",
                    "Pagamento PIX com dados do devedor",
                    "Pagamento cartão com dados do portador"
                ],
                "data_sources": [
                    "customer_* fields (dados diretos)",
                    "cardholder_name (nome do portador)",
                    "nome_devedor (nome do devedor PIX)",
                    "Dados de endereço opcionais"
                ]
            },
            "database_improvements": {
                "description": "Melhorias na estrutura do banco",
                "changes": [
                    "cartoes_tokenizados.cliente_id (UUID interno)",
                    "payments.cliente_id (UUID interno)",
                    "Relacionamentos opcionais",
                    "Compatibilidade com customer_id string",
                    "Índices para performance"
                ]
            }
        }

    return app

app = create_app()
__all__ = ["app", "create_app"]