import logging
import os
import hashlib

from ..database.supabase_storage import download_cert_file, ensure_folder_exists
from ..database.database import get_empresa_config
from ..core.config import settings

logger = logging.getLogger(__name__)

# 🔐 Caminho persistente para certificados no Render
BASE_CERT_DIR = "/data/certificados"


async def get_empresa_credentials(empresa_id: str):
    """
    Recupera as credenciais da empresa para uso com Sicredi, Rede e Asaas.
    """
    try:
        config = await get_empresa_config(empresa_id)
        if not config:
            logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada.")
            return None

        credentials = {
            "asaas_api_key": config.get("asaas_api_key"),
            "sicredi_client_id": config.get("sicredi_client_id"),
            "sicredi_client_secret": config.get("sicredi_client_secret"),
            "sicredi_api_key": config.get("sicredi_api_key"),
            "rede_pv": config.get("rede_pv"),
            "rede_api_key": config.get("rede_api_key"),
            "webhook_pix": config.get("webhook_pix"),
            "sicredi_env": config.get("sicredi_env", "production"),
        }

        missing = [k for k in ["sicredi_client_id", "sicredi_client_secret"] if not credentials.get(k)]
        if missing:
            logger.warning(f"⚠️ Credenciais sensíveis ausentes para empresa {empresa_id}: {missing}")

        logger.debug(f"🔐 Credenciais carregadas para empresa {empresa_id}: "
                     f"{[k for k, v in credentials.items() if v is not None]}")

        return credentials

    except Exception as e:
        logger.error(f"❌ Erro ao obter credenciais da empresa {empresa_id}: {str(e)}")
        return None


async def create_temp_cert_files(empresa_id: str):
    """
    Garante que os certificados da empresa existam localmente,
    baixando do Supabase Storage e criando a pasta se necessário.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais não encontradas para empresa {empresa_id}")

        await ensure_folder_exists(empresa_id=empresa_id, bucket=settings.SUPABASE_BUCKET)

        empresa_path = os.path.join(BASE_CERT_DIR, empresa_id)
        os.makedirs(empresa_path, exist_ok=True)

        mapping = {
            "cert_path": "sicredi-cert.pem",
            "key_path": "sicredi-key.key",  # ✅ Correto
            "ca_path": "sicredi-ca.pem",
        }

        file_paths = {}

        for key, filename in mapping.items():
            full_path = os.path.join(empresa_path, filename)

            if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
                logger.info(f"📥 Tentando baixar {filename} do Supabase para empresa {empresa_id}...")
                success = await download_cert_file(empresa_id=empresa_id, filename=filename, dest_path=full_path)
                if not success:
                    logger.warning(f"⚠️ {filename} não encontrado ou inválido no Supabase Storage.")
                    continue

            # Validação de integridade do arquivo
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
                    if not content.strip() or b"-----BEGIN" not in content:
                        logger.warning(f"⚠️ {filename} vazio ou malformado em {full_path}")
                        continue
                    hash_digest = hashlib.md5(content).hexdigest()
                    logger.info(f"📄 {filename} válido (md5: {hash_digest})")
                    file_paths[key] = full_path
            except Exception as e:
                logger.warning(f"⚠️ Erro ao validar {filename}: {str(e)}")

        if "cert_path" not in file_paths or "key_path" not in file_paths:
            raise ValueError(f"❌ Certificados essenciais ausentes para empresa {empresa_id}")

        def cleanup():
            logger.debug("🧹 Nenhum cleanup necessário — certificados persistem em disco.")

        file_paths["cleanup"] = cleanup
        return file_paths

    except Exception as e:
        logger.error(f"❌ Erro ao preparar certificados da empresa {empresa_id}: {str(e)}")
        return None
