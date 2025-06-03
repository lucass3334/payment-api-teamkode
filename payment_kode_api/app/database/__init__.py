# payment_kode_api/app/database/__init__.py

# 🔧 CORRIGIDO: Definir variável de controle globalmente
_customers_management_available = False

try:
    # Métodos principais do banco de dados
    from .database import (
        # Pagamentos
        save_payment,
        get_payment,
        get_payment_by_txid,
        update_payment_status,  # 🔧 ADICIONADO: Método principal de atualização
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
        get_or_create_asaas_customer
    )

    # 🔧 ADICIONADO: Importação do Supabase client para uso direto quando necessário
    from .supabase_client import supabase

    # 🔧 ADICIONADO: Importação dos métodos de storage
    from .supabase_storage import (
        upload_cert_file,
        download_cert_file,
        ensure_folder_exists,
        SUPABASE_BUCKET
    )

except ImportError as e:
    raise RuntimeError(f"Erro crítico na inicialização do módulo database: {str(e)}") from e


# 🔧 CORRIGIDO: Import separado para customers_management
try:
    from .customers_management import (
        get_or_create_cliente,
        get_cliente_by_external_id,
        get_cliente_by_cpf_cnpj,
        get_cliente_by_email,
        get_cliente_by_id,
        create_or_update_endereco,
        get_enderecos_cliente,
        get_endereco_principal_cliente,
        update_cliente,
        list_clientes_empresa,
        delete_cliente,
        search_clientes,
        get_cliente_stats_summary,
        extract_customer_data_from_payment,
        # Funções auxiliares
        extract_cpf_cnpj,
        extract_nome,
        extract_telefone,
        has_address_data,
        extract_address_data,
        generate_external_id
    )
    _customers_management_available = True
except ImportError as e:
    print(f"⚠️ Módulo customers_management não disponível: {e}")
    _customers_management_available = False
    
    # Definir funções dummy para evitar erros de import
    async def get_or_create_cliente(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_cliente_by_external_id(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_cliente_by_cpf_cnpj(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_cliente_by_email(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_cliente_by_id(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def create_or_update_endereco(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_enderecos_cliente(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_endereco_principal_cliente(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def update_cliente(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def list_clientes_empresa(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def delete_cliente(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def search_clientes(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    async def get_cliente_stats_summary(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def extract_customer_data_from_payment(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def extract_cpf_cnpj(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def extract_nome(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def extract_telefone(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def has_address_data(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def extract_address_data(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")
    def generate_external_id(*args, **kwargs):
        raise NotImplementedError("Módulo customers_management não disponível")


def init_database():
    """Configura e valida as conexões do módulo de banco de dados."""
    try:
        required_methods = [
            # Pagamentos
            save_payment,
            get_payment,
            get_payment_by_txid,
            update_payment_status,  # 🔧 ADICIONADO
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
            
            # 🔧 ADICIONADO: Storage methods
            upload_cert_file,
            download_cert_file,
            ensure_folder_exists,
        ]
        
        # 🔧 ADICIONADO: Verificar disponibilidade de customers_management
        if _customers_management_available:
            required_methods.extend([
                get_or_create_cliente,
                get_cliente_by_external_id,
                get_cliente_by_cpf_cnpj,
                get_cliente_by_email,
                get_cliente_by_id,
                create_or_update_endereco,
                get_enderecos_cliente,
                get_endereco_principal_cliente,
                update_cliente,
                list_clientes_empresa,
                delete_cliente,
                search_clientes,
                get_cliente_stats_summary,
                extract_customer_data_from_payment,
            ])
        
        # 🔧 MELHORADO: Verificação mais robusta
        missing_methods = [method.__name__ for method in required_methods if method is None]
        if missing_methods:
            raise ImportError(f"Métodos essenciais não carregados: {missing_methods}")

        # 🔧 ADICIONADO: Verificação da conexão Supabase
        if supabase is None:
            raise ImportError("Cliente Supabase não foi inicializado corretamente")

        print("✅ Módulo database inicializado com sucesso")
        print(f"📦 Bucket configurado: {SUPABASE_BUCKET}")
        if _customers_management_available:
            print("👥 Módulo customers_management disponível")
        else:
            print("⚠️ Módulo customers_management NÃO disponível")

    except Exception as e:
        print(f"❌ Falha na inicialização do database: {str(e)}")
        raise


def shutdown_database():
    """Encerra conexões do banco de dados de forma segura."""
    try:
        # Redis desativado — encerramento removido
        # get_redis_client().close()
        
        # Supabase não precisa de encerramento explícito
        # mas podemos limpar variáveis globais se necessário
        
        print("✅ Conexões do database encerradas")
    except Exception as e:
        print(f"⚠️ Erro ao encerrar conexões: {str(e)}")


# 🔧 ADICIONADO: Função de utilidade para verificar saúde do banco
async def health_check_database():
    """Verifica se o banco de dados está acessível."""
    try:
        # Teste básico com Supabase
        response = supabase.table("empresas").select("empresa_id").limit(1).execute()
        return {"status": "healthy", "message": "Database connection OK"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Database error: {str(e)}"}


__all__ = [
    # Pagamentos
    "save_payment",
    "get_payment",
    "get_payment_by_txid",
    "update_payment_status",  # 🔧 ADICIONADO
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
    "get_or_create_asaas_customer",
    
    # 🔧 ADICIONADO: Storage
    "upload_cert_file",
    "download_cert_file",
    "ensure_folder_exists",
    "SUPABASE_BUCKET",
    
    # 🔧 ADICIONADO: Cliente Supabase
    "supabase",
    
    # Inicialização/Desligamento
    "init_database",
    "shutdown_database",
    "health_check_database",  # 🔧 ADICIONADO
]

# 🔧 ADICIONADO: Adicionar exports condicionais de customers_management
if _customers_management_available:
    __all__.extend([
        "get_or_create_cliente",
        "get_cliente_by_external_id",
        "get_cliente_by_cpf_cnpj",
        "get_cliente_by_email",
        "get_cliente_by_id",
        "create_or_update_endereco",
        "get_enderecos_cliente",
        "get_endereco_principal_cliente",
        "update_cliente",
        "list_clientes_empresa",
        "delete_cliente",
        "search_clientes",
        "get_cliente_stats_summary",
        "extract_customer_data_from_payment",
        # Funções auxiliares de clientes
        "extract_cpf_cnpj",
        "extract_nome",
        "extract_telefone",
        "has_address_data",
        "extract_address_data",
        "generate_external_id",
    ])