from pydantic import AnyHttpUrl, Field, ValidationError
from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import urlparse, quote_plus
import ssl
from loguru import logger

class Settings(BaseSettings):
    """Configurações globais da aplicação carregadas de variáveis de ambiente."""

    # 🔹 Banco de Dados e Cache
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(..., env="SUPABASE_KEY")

    # 🔹 Configuração do Redis
    REDIS_URL: Optional[str] = Field(None, env="REDIS_URL")
    REDIS_HOST: str = Field("redis", env="REDIS_HOST")
    REDIS_PORT: int = Field(6379, env="REDIS_PORT")
    REDIS_USERNAME: Optional[str] = Field(None, env="REDIS_USERNAME")
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(0, env="REDIS_DB")

    REDIS_USE_SSL: bool = Field(False, env="REDIS_USE_SSL")
    REDIS_SSL_CERT_REQS: str = Field("CERT_NONE", env="REDIS_SSL_CERT_REQS")

    # 🔹 Controle de Ambiente
    USE_SANDBOX: bool = Field(True, env="USE_SANDBOX")

    # 🔹 Suporte a Multiempresas
    EMPRESA_ID: Optional[str] = Field(None, env="EMPRESA_ID")

    # 🔹 Configuração de Webhooks
    WEBHOOK_PIX: Optional[AnyHttpUrl] = Field(None, env="WEBHOOK_PIX")

    # 🔹 Configuração do ambiente do Sicredi
    SICREDI_ENV: str = Field("production", env="SICREDI_ENV")

    # 🔹 Depuração
    DEBUG: bool = Field(False, env="DEBUG")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def configure_redis(self):
        """Configura Redis com SSL e autenticação correta para Render.com"""
        if self.REDIS_URL:
            parsed_url = urlparse(self.REDIS_URL)

            # 🔹 Captura corretamente usuário e senha do Redis
            self.REDIS_USERNAME = parsed_url.username or self.REDIS_USERNAME
            self.REDIS_PASSWORD = quote_plus(parsed_url.password) if parsed_url.password else self.REDIS_PASSWORD

            # 🔹 Ajusta host e porta corretamente
            self.REDIS_HOST = parsed_url.hostname or "redis"
            self.REDIS_PORT = parsed_url.port or 6379
            self.REDIS_DB = int(parsed_url.path.lstrip("/") or self.REDIS_DB)

            # 🔹 Reconstrói a URL correta para Celery e outros serviços
            self.REDIS_URL = f"rediss://{self.REDIS_USERNAME}:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

            # 🔹 Ativa SSL se necessário
            self.REDIS_USE_SSL = parsed_url.scheme == "rediss"
            if self.REDIS_USE_SSL:
                self.REDIS_SSL_CERT_REQS = "CERT_NONE"  # ✅ Evita problemas de certificado

        # 🔹 Mapeia certificados SSL corretamente
        ssl_cert_map = {
            "CERT_NONE": ssl.CERT_NONE,
            "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
            "CERT_REQUIRED": ssl.CERT_REQUIRED
        }
        self.REDIS_SSL_CERT_REQS = ssl_cert_map.get(self.REDIS_SSL_CERT_REQS.upper(), ssl.CERT_NONE)

        # 🔹 Garante que `REDIS_USE_SSL` seja booleano
        self.REDIS_USE_SSL = str(self.REDIS_USE_SSL).lower() in ["true", "1"]

        logger.info("🔍 Configuração do Redis carregada:")
        logger.info(f"  - Host: {self.REDIS_HOST}")
        logger.info(f"  - Porta: {self.REDIS_PORT}")
        logger.info(f"  - Banco: {self.REDIS_DB}")
        logger.info(f"  - SSL: {'Ativado' if self.REDIS_USE_SSL else 'Desativado'}")
        logger.info(f"  - Usuário: {self.REDIS_USERNAME}")
        logger.info(f"  - URL Redis reconstruída: {self.REDIS_URL.replace(self.REDIS_PASSWORD, '[REDACTED]') if self.REDIS_PASSWORD else '⚠ Sem senha definida!'}")

# ✅ Instância de configurações apenas quando necessário
try:
    settings = Settings()
    settings.configure_redis()
except ValidationError as e:
    logger.error(f"❌ Erro na configuração: {e}")
    raise
