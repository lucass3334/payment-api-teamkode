# payment_kode_api/app/database/supabase_storage.py

import logging
from typing import Optional
from supabase import create_client, Client
from payment_kode_api.app.core.config import settings

logger = logging.getLogger(__name__)

SUPABASE_BUCKET = settings.SUPABASE_BUCKET


class SupabaseStorageClient:
    _client: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._client is None:
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client.storage


storage_client = SupabaseStorageClient.get_client()


async def ensure_folder_exists(empresa_id: str, bucket: str = SUPABASE_BUCKET) -> bool:
    """
    Garante que a 'pasta lógica' no bucket da empresa exista.
    Usa upload de um arquivo .init vazio para simular diretório.
    """
    folder_prefix = f"{empresa_id}/"
    init_path = f"{folder_prefix}.init"

    try:
        existing = storage_client.from_(bucket).list(path=folder_prefix)
        if existing and isinstance(existing, list):
            logger.info(f"📁 Pasta lógica '{folder_prefix}' já existe no bucket '{bucket}'.")
            return True

        storage_client.from_(bucket).upload(
            path=init_path,
            file=b"",
            file_options={"content-type": "text/plain"}
        )
        logger.info(f"✅ Placeholder '.init' criado para empresa {empresa_id} em {bucket}/{folder_prefix}")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao criar diretório lógico '{folder_prefix}' no bucket {bucket}: {str(e)}")
        return False


async def download_cert_file(empresa_id: str, filename: str) -> Optional[bytes]:
    """
    Faz o download de um certificado como bytes diretamente da memória.
    Retorna None se o conteúdo for inválido ou não encontrado.
    """
    storage_path = f"{empresa_id}/{filename}"
    try:
        logger.info(f"📦 Baixando {filename} do path {storage_path}...")

        file_bytes = storage_client.from_(SUPABASE_BUCKET).download(storage_path)

        if not file_bytes or not isinstance(file_bytes, bytes) or len(file_bytes) < 20:
            logger.warning(f"⚠️ {filename} vazio, inválido ou não encontrado para empresa {empresa_id}.")
            return None

        logger.info(f"✅ {filename} baixado com sucesso para empresa {empresa_id}.")
        return file_bytes

    except Exception as e:
        logger.error(f"❌ Erro ao baixar {filename} de {SUPABASE_BUCKET}/{empresa_id}: {str(e)}")
        return None


async def upload_cert_file(empresa_id: str, filename: str, file_bytes: bytes) -> bool:
    """
    Faz o upload de um certificado .pem ou .key para o Supabase Storage.
    """
    path = f"{empresa_id}/{filename}"

    try:
        logger.info(f"🚀 Upload do certificado {filename} para {SUPABASE_BUCKET}/{path}")

        storage_client.from_(SUPABASE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": "application/x-pem-file"}
        )

        logger.info(f"✅ Upload bem-sucedido de {filename} para {empresa_id}.")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao fazer upload de {filename} para empresa {empresa_id}: {str(e)}")
        return False
