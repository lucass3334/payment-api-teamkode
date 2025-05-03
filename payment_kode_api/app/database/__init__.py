# payment_kode_api/app/database/__init__.py

try:
    # Métodos principais do banco de dados
    from .database import (
        # Pagamentos
        save_payment,
        get_payment,
        get_payment_by_txid,
        update_payment_status_by_txid,
        # Empresas
        save_empresa,
        get_empresa,
        get_empresa_by_token,
        get_empresa_by_chave_pix,
        get_empresa_config,
        # Cartões
        save_tokenized_card,
        get_tokenized_card,
        delete_tokenized_card,
        # Certificados RSA
        get_empresa_certificados,
        save_empresa_certificados,
        # Gateways
        atualizar_config_gateway,
        get_empresa_gateways,
        # Sicredi
        get_sicredi_token_or_refresh,
    )

    # Métodos de mapeamento Asaas Customers
    from .customers import (
        get_asaas_customer,
        save_asaas_customer,
    )

    # Redis desativado — mantendo como referência
    # from .redis_client import get_redis_client, test_redis_connection

except ImportError as e:
    raise RuntimeError(f"Erro crítico na inicialização do módulo database: {str(e)}") from e


def init_database():
    """Configura e valida as conexões do módulo de banco de dados."""
    try:
        required_methods = [
            save_payment,
            get_payment,
            get_payment_by_txid,
            update_payment_status_by_txid,
            save_empresa,
            get_empresa,
            get_empresa_by_token,
            get_empresa_by_chave_pix,
            get_empresa_config,
            save_tokenized_card,
            get_tokenized_card,
            delete_tokenized_card,
            get_empresa_certificados,
            save_empresa_certificados,
            atualizar_config_gateway,
            get_empresa_gateways,
            get_sicredi_token_or_refresh,
            # Asaas customers
            get_asaas_customer,
            save_asaas_customer,
        ]
        if None in required_methods:
            raise ImportError("Métodos essenciais do banco de dados não carregados")

        print("✅ Módulo database inicializado com sucesso")

    except Exception as e:
        print(f"❌ Falha na inicialização do database: {str(e)}")
        raise


def shutdown_database():
    """Encerra conexões do banco de dados de forma segura."""
    try:
        # Redis desativado — encerramento removido
        # get_redis_client().close()
        print("✅ Conexões do database encerradas")
    except Exception as e:
        print(f"⚠️ Erro ao encerrar conexões: {str(e)}")


__all__ = [
    # Pagamentos
    "save_payment",
    "get_payment",
    "get_payment_by_txid",
    "update_payment_status_by_txid",
    # Empresas
    "save_empresa",
    "get_empresa",
    "get_empresa_by_token",
    "get_empresa_by_chave_pix",
    "get_empresa_config",
    # Cartões
    "save_tokenized_card",
    "get_tokenized_card",
    "delete_tokenized_card",
    # Certificados RSA
    "get_empresa_certificados",
    "save_empresa_certificados",
    # Gateways
    "atualizar_config_gateway",
    "get_empresa_gateways",
    # Sicredi
    "get_sicredi_token_or_refresh",
    # Asaas Customers
    "get_asaas_customer",
    "save_asaas_customer",
    # Inicialização/Desligamento
    "init_database",
    "shutdown_database",
]
