import base64
import tempfile
import logging
import os
from ..database.database import get_empresa_config, get_empresa_certificados

logger = logging.getLogger(__name__)


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
    Gera arquivos temporários de certificados (.pem) a partir de strings base64.
    Retorna os caminhos desses arquivos e uma função 'cleanup' para removê-los.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais não encontradas para empresa {empresa_id}")

        mapping = {
            "cert_path": ("sicredi_cert_base64", "sicredi-cert.pem"),
            "key_path": ("sicredi_key_base64", "sicredi-key.pem"),
        }

        temp_files = {}

        for key_name, (b64_key, filename) in mapping.items():
            encoded_data = credentials.get(b64_key)
            if not encoded_data:
                logger.warning(f"⚠️ Certificado {b64_key} ausente para empresa {empresa_id}")
                continue

            try:
                decoded = base64.b64decode(encoded_data).decode("utf-8")
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"-{filename}", mode="wt", encoding="utf-8") as temp:
                    temp.write(decoded)
                    temp.flush()
                    temp_files[key_name] = temp.name
                    logger.info(f"📄 Certificado {filename} salvo temporariamente: {temp.name}")
                    logger.debug(f"📄 Conteúdo de {filename} (início):\n{decoded[:300]}")
            except Exception as decode_error:
                logger.error(f"❌ Falha ao processar {filename} da empresa {empresa_id}: {decode_error}")

        if "cert_path" not in temp_files or "key_path" not in temp_files:
            raise ValueError(f"❌ Certificados insuficientes para empresa {empresa_id}")

        def cleanup():
            for path in temp_files.values():
                if isinstance(path, str):
                    try:
                        os.remove(path)
                        logger.info(f"🧹 Certificado temporário removido: {path}")
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao tentar remover {path}: {e}")

        temp_files["cleanup"] = cleanup
        return temp_files

    except Exception as e:
        logger.error(f"❌ Erro ao gerar arquivos temporários para empresa {empresa_id}: {str(e)}")
        return None
