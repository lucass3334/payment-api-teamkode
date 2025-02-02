from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import urlparse
import ssl

class Settings(BaseSettings):
    """Configurações globais da aplicação carregadas de variáveis de ambiente."""

    # 🔹 Banco de Dados e Cache
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(..., env="SUPABASE_KEY")

    # 🔹 Configuração do Redis
    REDIS_URL: Optional[str] = Field(None, env="REDIS_URL")
    REDIS_HOST: str = Field("localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(6379, env="REDIS_PORT")
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(0, env="REDIS_DB")
    
    REDIS_USE_SSL: bool = Field(False, env="REDIS_USE_SSL")
    REDIS_SSL_CERT_REQS: str = Field("CERT_NONE", env="REDIS_SSL_CERT_REQS")

    # 🔹 Controle de Ambiente
    USE_SANDBOX: bool = Field(True, env="USE_SANDBOX")

    # 🔹 Suporte a Multiempresas
    EMPRESA_ID: Optional[str] = Field(None, env="EMPRESA_ID")

    # 🔹 Configuração de Webhooks
    WEBHOOK_PIX: AnyHttpUrl = Field(..., env="WEBHOOK_PIX")

    # 🔹 Configuração do ambiente do Sicredi (produção ou homologação)
    SICREDI_ENV: str = Field("production", env="SICREDI_ENV")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def configure_redis(self):
        """Configura o Redis com SSL e tratamento especial para Render.com"""
        if self.REDIS_URL:
            parsed_url = urlparse(self.REDIS_URL)

            # 🔹 Extrai password corretamente (incluindo caracteres especiais)
            self.REDIS_PASSWORD = parsed_url.password or self.REDIS_PASSWORD

            # 🔹 Força configurações SSL quando usar rediss://
            if parsed_url.scheme == "rediss":
                self.REDIS_USE_SSL = True
                self.REDIS_SSL_CERT_REQS = "CERT_NONE"

            self.REDIS_HOST = parsed_url.hostname or self.REDIS_HOST
            
            # 🔹 Correção: Remove espaços antes de converter para inteiro
            self.REDIS_PORT = int(parsed_url.port) if parsed_url.port else 6379  # ✅ Define um valor padrão seguro
            self.REDIS_DB = int(parsed_url.path.lstrip("/") or self.REDIS_DB)

        # 🔹 Converte `REDIS_SSL_CERT_REQS` para `ssl` corretamente
        ssl_cert_map = {
            "CERT_NONE": ssl.CERT_NONE,
            "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
            "CERT_REQUIRED": ssl.CERT_REQUIRED
        }
        self.REDIS_SSL_CERT_REQS = ssl_cert_map.get(self.REDIS_SSL_CERT_REQS.upper(), ssl.CERT_NONE)

# Instância única de configurações
settings = Settings()
settings.configure_redis()
