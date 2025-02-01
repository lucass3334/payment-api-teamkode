from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import urlparse

class Settings(BaseSettings):
    """Configurações globais da aplicação carregadas de variáveis de ambiente."""

    # 🔹 Banco de Dados e Cache
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(..., env="SUPABASE_KEY")

    # 🔹 Configuração do Redis (Usa URL completa se disponível, senão configura manualmente)
    REDIS_URL: Optional[str] = None
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    # 🔹 Controle de Ambiente
    USE_SANDBOX: bool = Field(True, env="USE_SANDBOX")

    # 🔹 Suporte a Multiempresas
    EMPRESA_ID: Optional[str] = None  # UUID opcional para multiempresas

    # 🔹 Configuração de Webhooks
    WEBHOOK_PIX: AnyHttpUrl = Field(..., env="WEBHOOK_PIX")  # Garante que a URL seja válida

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True  # Garante que os nomes das variáveis sejam case-sensitive

    def configure_redis(self):
        """Configura o Redis com base na URL ou nos parâmetros individuais."""
        if self.REDIS_URL:
            parsed_url = urlparse(self.REDIS_URL)
            self.REDIS_HOST = parsed_url.hostname
            self.REDIS_PORT = parsed_url.port
            self.REDIS_PASSWORD = parsed_url.password
            self.REDIS_DB = int(parsed_url.path.lstrip("/") or 0)

# Instância única de configurações
settings = Settings()

# Configura Redis corretamente se REDIS_URL estiver definida
settings.configure_redis()
