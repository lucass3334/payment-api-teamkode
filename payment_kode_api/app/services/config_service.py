import logging
import os
import hashlib
from typing import Optional

from ..database.supabase_storage import download_cert_file, ensure_folder_exists
from ..database.database import get_empresa_config
from ..core.config import settings

logger = logging.getLogger(__name__)

# 🔐 Caminho persistente para certificados no Render
BASE_CERT_DIR = "/data/certificados"

# 📁 Arquivos esperados
CERT_MAPPING = {
    "cert_path": "sicredi-cert.pem",
    "key_path": "sicredi-key.key",
    "ca_path": "sicredi-ca.pem",
}


async def get_empresa_credentials(empresa_id: str) -> Optional[dict]:
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


async def create_temp_cert_files(empresa_id: str) -> Optional[dict]:
    """
    Garante que os certificados da empresa existam localmente,
    baixando do Supabase Storage e validando o conteúdo.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais não encontradas para empresa {empresa_id}")

        await ensure_folder_exists(empresa_id=empresa_id, bucket=settings.SUPABASE_BUCKET)

        empresa_path = os.path.join(BASE_CERT_DIR, empresa_id)
        os.makedirs(empresa_path, exist_ok=True)

        file_paths = {}

        for key, filename in CERT_MAPPING.items():
            full_path = os.path.join(empresa_path, filename)

            # Tenta baixar do Supabase se não existir ou estiver vazio
            if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
                logger.info(f"📥 Tentando baixar {filename} do Supabase para empresa {empresa_id}...")
                success = await download_cert_file(
                    empresa_id=empresa_id,
                    filename=filename,
                    dest_path=full_path
                )
                if not success:
                    logger.warning(f"⚠️ {filename} não encontrado ou inválido no Supabase Storage.")
                    continue

            # Validação de conteúdo
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
                    if not content.strip() or b"-----BEGIN" not in content:
                        logger.warning(f"⚠️ {filename} vazio ou malformado: {full_path}")
                        continue

                    hash_digest = hashlib.md5(content).hexdigest()
                    logger.info(f"📄 {filename} válido (md5: {hash_digest})")
                    file_paths[key] = full_path

            except Exception as e:
                logger.warning(f"⚠️ Erro ao validar {filename}: {str(e)}")

        if "cert_path" not in file_paths or "key_path" not in file_paths:
            raise ValueError(f"❌ Certificados essenciais ausentes ou inválidos para empresa {empresa_id}")

        def cleanup():
            logger.debug("🧹 Nenhum cleanup necessário — certificados persistem em disco.")

        file_paths["cleanup"] = cleanup
        return file_paths

    except Exception as e:
        logger.error(f"❌ Erro ao preparar certificados da empresa {empresa_id}: {str(e)}")
        return None


def delete_temp_cert_files(empresa_id: str) -> bool:
    """
    Remove os certificados da empresa do disco local, se existirem.
    Útil para testes ou força de revalidação.
    """
    try:
        empresa_path = os.path.join(BASE_CERT_DIR, empresa_id)
        deleted_files = []

        for filename in CERT_MAPPING.values():
            full_path = os.path.join(empresa_path, filename)
            if os.path.exists(full_path):
                os.remove(full_path)
                deleted_files.append(filename)

        if deleted_files:
            logger.info(f"🗑️ Certificados deletados para empresa {empresa_id}: {deleted_files}")
        else:
            logger.info(f"ℹ️ Nenhum certificado encontrado para deletar em {empresa_path}")

        return True

    except Exception as e:
        logger.error(f"❌ Erro ao deletar certificados da empresa {empresa_id}: {str(e)}")
        return False
