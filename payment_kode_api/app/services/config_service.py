import base64
import logging
import os
from ..database.database import get_empresa_config, get_empresa_certificados

logger = logging.getLogger(__name__)

# Caminho base persistente no disco do Render
BASE_CERT_DIR = "/data/certificados"


async def get_empresa_credentials(empresa_id: str):
    """
    Recupera as credenciais completas da empresa para uso em integrações com Sicredi, Rede e Asaas.
    """
    try:
        config = await get_empresa_config(empresa_id)
        if not config:
            logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada.")
            return None

        certificados = await get_empresa_certificados(empresa_id) or {}

        credentials = {
            "asaas_api_key": config.get("asaas_api_key"),
            "sicredi_client_id": config.get("sicredi_client_id"),
            "sicredi_client_secret": config.get("sicredi_client_secret"),
            "sicredi_api_key": config.get("sicredi_api_key"),
            "rede_pv": config.get("rede_pv"),
            "rede_api_key": config.get("rede_api_key"),
            "sicredi_cert_base64": certificados.get("sicredi_cert_base64"),
            "sicredi_key_base64": certificados.get("sicredi_key_base64"),
            "sicredi_ca_base64": certificados.get("sicredi_ca_base64"),  # opcional
            "webhook_pix": config.get("webhook_pix"),
            "sicredi_env": config.get("sicredi_env", "production"),
        }

        missing = [k for k in ["sicredi_cert_base64", "sicredi_key_base64"] if not credentials.get(k)]
        if missing:
            logger.warning(f"⚠️ Certificados ausentes para empresa {empresa_id}: {missing}")

        logger.debug(f"🔐 Credenciais recuperadas para empresa {empresa_id}: "
                     f"{[k for k, v in credentials.items() if v is not None]}")

        return credentials

    except Exception as e:
        logger.error(f"❌ Erro ao obter credenciais da empresa {empresa_id}: {str(e)}")
        return None


async def create_temp_cert_files(empresa_id: str):
    """
    Gera arquivos de certificado persistentes em /data/certificados/<empresa_id>.
    Retorna os caminhos dos arquivos e uma função dummy de cleanup.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais não encontradas para empresa {empresa_id}")

        empresa_path = os.path.join(BASE_CERT_DIR, empresa_id)
        os.makedirs(empresa_path, exist_ok=True)

        mapping = {
            "cert_path": ("sicredi_cert_base64", "sicredi-cert.pem"),
            "key_path": ("sicredi_key_base64", "sicredi-key.pem"),
        }

        file_paths = {}

        for key, (cred_key, filename) in mapping.items():
            b64_data = credentials.get(cred_key)
            full_path = os.path.join(empresa_path, filename)

            if not b64_data:
                logger.warning(f"⚠️ {cred_key} ausente para empresa {empresa_id}")
                continue

            if not os.path.exists(full_path):
                try:
                    decoded = base64.b64decode(b64_data).decode("utf-8")
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(decoded)
                    logger.info(f"📄 Certificado salvo em: {full_path}")
                    logger.debug(f"📄 Conteúdo de {filename} (início):\n{decoded[:300]}")
                except Exception as e:
                    logger.error(f"❌ Falha ao salvar {filename} da empresa {empresa_id}: {e}")
                    raise

            file_paths[key] = full_path

        if "cert_path" not in file_paths or "key_path" not in file_paths:
            raise ValueError(f"❌ Certificados insuficientes para empresa {empresa_id}")

        def cleanup():
            logger.debug("🧹 Nenhum cleanup necessário — certificados persistem em disco.")

        file_paths["cleanup"] = cleanup
        return file_paths

    except Exception as e:
        logger.error(f"❌ Erro ao preparar certificados para empresa {empresa_id}: {str(e)}")
        return None
