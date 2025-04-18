# payment_kode_api/app/database/__init__.py

try:
    # Métodos principais do banco de dados
    from .database import (
        save_payment,
        get_payment,
        update_payment_status,
        save_empresa,
        get_empresa_by_chave_pix,
        get_empresa_config,
        get_tokenized_card,
        get_empresa_certificados,      # 🔹 Adicionado
        save_empresa_certificados      # 🔹 Adicionado
    )

    # Cliente Redis com inicialização controlada
    from .redis_client import get_redis_client, test_redis_connection

except ImportError as e:
    raise RuntimeError(f"Erro crítico na inicialização do módulo database: {str(e)}") from e

def init_database():
    """Configura e valida as conexões do módulo de banco de dados"""
    try:
        if not test_redis_connection():
            raise ConnectionError("Falha na conexão com Redis")

        required_methods = [
            save_payment,
            get_payment,
            update_payment_status,
            get_tokenized_card,
            get_empresa_by_chave_pix,
            get_empresa_config,
            get_empresa_certificados,
            save_empresa_certificados
        ]
        if None in required_methods:
            raise ImportError("Métodos essenciais do banco de dados não carregados")

        print("✅ Módulo database inicializado com sucesso")

    except Exception as e:
        print(f"❌ Falha na inicialização do database: {str(e)}")
        raise

def shutdown_database():
    """Encerra conexões do banco de dados de forma segura"""
    try:
        get_redis_client().close()
        print("✅ Conexões do database encerradas")
    except Exception as e:
        print(f"⚠️ Erro ao encerrar conexões: {str(e)}")

__all__ = [
    "save_payment",
    "get_payment",
    "update_payment_status",
    "save_empresa",
    "get_empresa_config",
    "get_empresa_by_chave_pix",
    "get_tokenized_card",
    "get_empresa_certificados",      # 🔹 Adicionado
    "save_empresa_certificados",     # 🔹 Adicionado
    "get_redis_client",
    "init_database",
    "shutdown_database"
]
