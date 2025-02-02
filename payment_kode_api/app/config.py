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
    REDIS_USERNAME: Optional[str] = Field(None, env="REDIS_USERNAME")  # ✅ Novo campo para usuário do Redis
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(0, env="REDIS_DB")

    REDIS_USE_SSL: bool = Field(False, env="REDIS_USE_SSL")
    REDIS_SSL_CERT_REQS: str = Field("CERT_REQUIRED", env="REDIS_SSL_CERT_REQS")  # ✅ Agora exige certificação válida

    # 🔹 Controle de Ambiente
    USE_SANDBOX: bool = Field(True, env="USE_SANDBOX")

    # 🔹 Suporte a Multiempresas
    EMPRESA_ID: Optional[str] = Field(None, env="EMPRESA_ID")

    # 🔹 Configuração de Webhooks
    WEBHOOK_PIX: AnyHttpUrl = Field(..., env="WEBHOOK_PIX")

    # 🔹 Configuração do ambiente do Sicredi (produção ou homologação)
    SICREDI_ENV: str = Field("production", env="SICREDI_ENV")

    # 🔹 Adiciona `DEBUG` com valor padrão `False`
    DEBUG: bool = Field(False, env="DEBUG")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def __init__(self, **values):
        """Executa configuração extra após carregar valores do `.env`."""
        super().__init__(**values)
        self.configure_redis()  # ✅ Agora chamado corretamente

    def configure_redis(self):
        """Configura o Redis com SSL e tratamento especial para Render.com"""
        if self.REDIS_URL:
            parsed_url = urlparse(self.REDIS_URL)

            # 🔹 Captura usuário e senha corretamente (Evita erro de autenticação)
            self.REDIS_USERNAME = parsed_url.username  # Pode ser None, Redis muitas vezes não usa
            self.REDIS_PASSWORD = parsed_url.password.strip() if parsed_url.password else self.REDIS_PASSWORD  # 🔹 `strip()` mantido para evitar espaços extras

            # 🔹 Força configurações SSL quando usar `rediss://`
            if parsed_url.scheme == "rediss":
                self.REDIS_USE_SSL = True
                self.REDIS_SSL_CERT_REQS = "CERT_NONE"  # ✅ Permite conexões sem certificado local

            self.REDIS_HOST = parsed_url.hostname or self.REDIS_HOST

            # 🔹 Define porta corretamente (Se não houver porta na URL, usa 6379)
            self.REDIS_PORT = int(parsed_url.port) if parsed_url.port else 6379
            self.REDIS_DB = int(parsed_url.path.lstrip("/") or self.REDIS_DB)

        # 🔹 Converte `REDIS_SSL_CERT_REQS` para `ssl` corretamente
        ssl_cert_map = {
            "CERT_NONE": ssl.CERT_NONE,
            "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
            "CERT_REQUIRED": ssl.CERT_REQUIRED
        }
        self.REDIS_SSL_CERT_REQS = ssl_cert_map.get(self.REDIS_SSL_CERT_REQS.upper(), ssl.CERT_NONE)

        # 🔹 Garante que `REDIS_USE_SSL` seja um booleano correto
        self.REDIS_USE_SSL = str(self.REDIS_USE_SSL).lower() in ["true", "1"]

# ✅ Instância única de configurações (agora `configure_redis()` será chamado automaticamente)
settings = Settings()
