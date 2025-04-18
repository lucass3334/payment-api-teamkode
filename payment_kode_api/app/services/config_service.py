import logging
import hashlib
from typing import Optional, Dict

from ..database.supabase_storage import download_cert_file, ensure_folder_exists
from ..database.database import get_empresa_config
from ..core.config import settings

logger = logging.getLogger(__name__)

# 🔐 Arquivos esperados no Supabase por empresa
CERT_MAPPING = {
    "cert_path": "sicredi-cert.pem",
    "key_path": "sicredi-key.key",
    "ca_path": "sicredi-ca.pem",
}


async def get_empresa_credentials(empresa_id: str) -> Optional[Dict[str, str]]:
    """
    Retorna as credenciais da empresa para integração com gateways (Sicredi, Rede, Asaas).
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

        logger.debug(
            f"🔐 Credenciais carregadas para empresa {empresa_id}: "
            f"{[k for k, v in credentials.items() if v is not None]}"
        )

        return credentials

    except Exception as e:
        logger.error(f"❌ Erro ao obter credenciais da empresa {empresa_id}: {str(e)}")
        return None


async def load_certificates_from_bucket(empresa_id: str) -> Optional[Dict[str, bytes]]:
    """
    Carrega os certificados Sicredi diretamente da memória via Supabase Storage.
    Retorna um dicionário com os conteúdos dos arquivos .pem/.key.
    """
    try:
        credentials = await get_empresa_credentials(empresa_id)
        if not credentials:
            raise ValueError(f"❌ Credenciais não encontradas para empresa {empresa_id}")

        await ensure_folder_exists(empresa_id=empresa_id)

        certs: Dict[str, bytes] = {}

        for key, filename in CERT_MAPPING.items():
            logger.info(f"📥 [{empresa_id}] Baixando {filename} do bucket...")

            content = await download_cert_file(empresa_id, filename)

            if not content or not content.strip():
                logger.warning(f"⚠️ [{empresa_id}] {filename} está vazio ou não encontrado.")
                continue

            if b"-----BEGIN" not in content:
                logger.warning(f"⚠️ [{empresa_id}] {filename} não contém um header PEM válido.")
                continue

            hash_digest = hashlib.md5(content).hexdigest()
            logger.info(f"📄 [{empresa_id}] {filename} válido (md5: {hash_digest})")
            certs[key] = content

        if "cert_path" not in certs or "key_path" not in certs:
            raise ValueError(f"❌ [{empresa_id}] Certificados essenciais ausentes ou inválidos.")

        return certs

    except Exception as e:
        logger.error(f"❌ Erro ao carregar certificados da empresa {empresa_id}: {str(e)}")
        return None
