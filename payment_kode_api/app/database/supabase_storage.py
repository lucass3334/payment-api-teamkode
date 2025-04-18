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
storage_client = create_client(SUPABASE_URL, SUPABASE_KEY).storage


async def ensure_folder_exists(empresa_id: str, bucket: str = SUPABASE_BUCKET) -> bool:
    """
    Cria uma "pasta lógica" no bucket do Supabase Storage para uma empresa,
    usando um arquivo placeholder (".init").

    Args:
        empresa_id (str): ID da empresa (UUID)
        bucket (str): Nome do bucket

    Returns:
        bool: True se a pasta foi criada ou já existia, False se houve erro
    """
    try:
        folder_prefix = f"{empresa_id}/"
        test_path = f"{folder_prefix}.init"

        # Verifica se já existe algo na pasta
        existing = storage_client.from_(bucket).list(path=folder_prefix)
        if existing:
            logger.info(f"📁 Pasta {folder_prefix} já existe no bucket {bucket}.")
            return True

        # Upload de placeholder para criar a pasta
        storage_client.from_(bucket).upload(
            path=test_path,
            file=b"",  # conteúdo vazio
            file_options={"content-type": "text/plain", "upsert": True}
        )

        logger.info(f"✅ Pasta {folder_prefix} criada com placeholder no bucket {bucket}.")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao criar pasta para empresa {empresa_id} no bucket {bucket}: {e}")
        return False


async def download_cert_file(empresa_id: str, filename: str, dest_path: str) -> bool:
    """
    Faz o download de um certificado do Supabase Storage para o disco local.
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
