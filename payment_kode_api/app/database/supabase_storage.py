# payment_kode_api/app/database/supabase_storage.py

import os
import logging
from supabase import create_client
from pathlib import Path

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "certificados"

# Inicializa o cliente do Supabase Storage
storage_client = create_client(SUPABASE_URL, SUPABASE_KEY).storage()

async def download_cert_file(empresa_id: str, filename: str, dest_path: str) -> bool:
    """
    Faz o download de um certificado do Supabase Storage para o disco local.

    Args:
        empresa_id (str): ID da empresa (UUID).
        filename (str): Nome do arquivo no bucket.
        dest_path (str): Caminho local onde o arquivo deve ser salvo.

    Returns:
        bool: True se sucesso, False se falhar.
    """
    try:
        storage_path = f"{empresa_id}/{filename}"
        logger.info(f"📦 Baixando {filename} de {storage_path} no Supabase Storage...")

        response = storage_client.from_(SUPABASE_BUCKET).download(storage_path)
        if response is None or not response.content:
            logger.error(f"❌ Conteúdo vazio ou não encontrado para {storage_path}")
            return False

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(response.content)

        os.chmod(dest_path, 0o600)
        logger.info(f"✅ Certificado salvo localmente em {dest_path}")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao baixar {filename} para empresa {empresa_id}: {str(e)}")
        return False


async def upload_cert_file(empresa_id: str, filename: str, file_bytes: bytes) -> bool:
    """
    Faz o upload de um certificado .pem/.key para o Supabase Storage.

    Args:
        empresa_id (str): ID da empresa (UUID).
        filename (str): Nome do arquivo (ex: sicredi-cert.pem).
        file_bytes (bytes): Conteúdo do arquivo.

    Returns:
        bool: True se o upload for bem-sucedido, False caso contrário.
    """
    try:
        path = f"{empresa_id}/{filename}"
        logger.info(f"🚀 Enviando {filename} para {path} no bucket {SUPABASE_BUCKET}")

        storage_client.from_(SUPABASE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": "application/x-pem-file", "upsert": True}
        )

        logger.info(f"✅ {filename} enviado com sucesso para {path}")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao enviar {filename} para empresa {empresa_id}: {e}")
        return False
