import logging
import hashlib
import ssl
from typing import Dict, Any, Optional

from ..database.supabase_storage import download_cert_file, ensure_folder_exists
from ..database.supabase_client import supabase
from ..core.config import settings

logger = logging.getLogger(__name__)

# 🔐 Mapeamento dos arquivos de certificado esperados no bucket
CERT_MAPPING = {
    "cert_path": "sicredi-cert.pem",
    "key_path":  "sicredi-key.key",
    "ca_path":   "sicredi-ca.pem",
}


async def get_empresa_config(empresa_id: str) -> Optional[Dict[str, Any]]:
    """
    Retorna a linha de configuração da empresa na tabela `empresas_config`.
    """
    try:
        resp = (
            supabase
            .table("empresas_config")
            .select("*")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar configuração da empresa {empresa_id}: {e}")
        raise


async def get_empresa_credentials(empresa_id: str) -> Dict[str, Any]:
    """
    Retorna as credenciais lógicas para gateways (Asaas, Sicredi, Rede) baseadas em `empresas_config`.
    """
    config = await get_empresa_config(empresa_id)
    if not config:
        logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada.")
        return {}

    creds = {
        "asaas_api_key":        config.get("asaas_api_key"),
        "sicredi_client_id":    config.get("sicredi_client_id"),
        "sicredi_client_secret":config.get("sicredi_client_secret"),
        "rede_pv":              config.get("rede_pv"),
        "rede_api_key":         config.get("rede_api_key"),
        "webhook_pix":          config.get("webhook_pix"),
        "sicredi_env":          config.get("sicredi_env", "production"),
    }

    # Avisar se faltar algo essencial
    missing = [k for k in ("sicredi_client_id", "sicredi_client_secret") if not creds.get(k)]
    if missing:
        logger.warning(f"⚠️ Credenciais ausentes para empresa {empresa_id}: {missing}")

    logger.debug(f"🔐 Credenciais carregadas para {empresa_id}: {[k for k,v in creds.items() if v]}")
    return creds


async def load_certificates_from_bucket(empresa_id: str) -> Dict[str, bytes]:
    """
    Baixa direto da Storage supabase os .pem/.key/.ca e retorna um dict com seus bytes.
    """
    # garante pasta local
    await ensure_folder_exists(empresa_id=empresa_id)

    certs: Dict[str, bytes] = {}
    for key, filename in CERT_MAPPING.items():
        logger.info(f"📥 [{empresa_id}] Baixando {filename}...")
        content = await download_cert_file(empresa_id, filename)

        if not content:
            logger.warning(f"⚠️ [{empresa_id}] {filename} não encontrado ou vazio.")
            continue
        if not content.startswith(b"-----BEGIN"):
            logger.warning(f"⚠️ [{empresa_id}] {filename} não é PEM válido.")
            continue

        md5 = hashlib.md5(content).hexdigest()
        logger.info(f"📄 [{empresa_id}] {filename} válido (md5={md5})")
        certs[key] = content

    # valida obrigatórios
    for required in ("cert_path", "key_path"):
        if required not in certs:
            raise ValueError(f"❌ [{empresa_id}] Certificado obrigatório faltando: {required}")

    return certs

def build_ssl_context_from_certs(certs: Dict[str, bytes]) -> ssl.SSLContext:
    """
    Cria um SSLContext mTLS a partir dos bytes dos certs carregados.
    """
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_verify_locations(cadata=certs["ca_path"].decode())
    # Para carregar a chave e o cert em memória precisamos gravá-los
    # temporariamente no disco ou usar TemporaryFile:
    import tempfile
    with tempfile.NamedTemporaryFile() as certf, tempfile.NamedTemporaryFile() as keyf:
        certf.write(certs["cert_path"]); certf.flush()
        keyf.write(certs["key_path"]);   keyf.flush()
        ctx.load_cert_chain(certfile=certf.name, keyfile=keyf.name)
    return ctx