from pydantic import BaseSettings

class Settings(BaseSettings):
    # Configurações da aplicação
    APP_NAME: str = "Payment Kode API"
    DEBUG: bool = True

    # Configurações do Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Configurações do Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Chaves de API dos Gateways
    SICREDI_API_KEY: str
    ASAAS_API_KEY: str
    REDE_API_KEY: str

    # Configurações adicionais
    GATEWAY_TIMEOUT: int = 30

    class Config:
        env_file = ".env"  # Arquivo que carrega variáveis de ambiente

settings = Settings()
