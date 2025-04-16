import base64
import tempfile
import logging
import os
from ..database.database import get_empresa_config, get_empresa_certificados

logger = logging.getLogger(__name__)


async def get_empresa_credentials(empresa_id: str):
    """
    Retorna todas as credenciais da empresa, incluindo chaves e certificados.
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
            "sicredi_env": config.get("sicredi_env", "production")
        }

        missing = [k for k in ["sicredi_cert_base64", "sicredi_key_base64"] if not credentials.get(k)]
        if missing:
            logger.warning(f"⚠️ Certificados ausentes para empresa {empresa_id}: {missing}")

        return credentials

    except Exception as e:
        logger.error(f"❌ Erro ao obter credenciais da empresa {empresa_id}: {str(e)}")
        return None


async def create_temp_cert_files(empresa_id: str):
    """
    Gera arquivos temporários com os certificados da empresa em disco e retorna seus caminhos.
    Inclui função de limpeza automática dos arquivos após uso.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais ausentes para empresa {empresa_id}")

        mapping = {
            "cert_path": ("sicredi_cert_base64", "sicredi-cert.pem"),
            "key_path": ("sicredi_key_base64", "sicredi-key.pem")
        }

        temp_files = {}

        for key_name, (encoded_key, filename) in mapping.items():
            cert_data = credentials.get(encoded_key)
            if not cert_data:
                logger.warning(f"⚠️ Certificado {encoded_key} ausente para empresa {empresa_id}")
                continue

            try:
                decoded = base64.b64decode(cert_data).decode("utf-8")
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"-{filename}", mode="wt", encoding="utf-8") as tmp:
                    tmp.write(decoded)
                    tmp.flush()
                    temp_files[key_name] = tmp.name
                    logger.info(f"📄 {filename} criado para empresa {empresa_id}: {tmp.name}")
            except Exception as cert_error:
                logger.error(f"❌ Erro ao processar {filename} da empresa {empresa_id}: {cert_error}")

        if "cert_path" not in temp_files or "key_path" not in temp_files:
            raise ValueError(f"❌ Certificados insuficientes para empresa {empresa_id}")

        def cleanup():
            for path in temp_files.values():
                if isinstance(path, str):
                    try:
                        os.remove(path)
                        logger.info(f"🧹 Certificado temporário removido: {path}")
                    except Exception as e:
                        logger.warning(f"⚠️ Falha ao remover {path}: {e}")

        temp_files["cleanup"] = cleanup
        return temp_files

    except Exception as e:
        logger.error(f"❌ Falha ao gerar arquivos temporários para empresa {empresa_id}: {str(e)}")
        return None
