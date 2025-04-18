from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from payment_kode_api.app.database.supabase_storage import upload_cert_file, ensure_folder_exists
from payment_kode_api.app.utilities.logging_config import logger
import os

router = APIRouter(prefix="/certificados", tags=["Certificados"])

ALLOWED_FILENAMES = {"sicredi-cert.pem", "sicredi-key.pem", "sicredi-ca.pem"}

@router.post("/upload")
async def upload_certificado(
    empresa_id: str = Form(...),
    arquivo: UploadFile = File(...)
):
    """
    Upload seguro de um arquivo .pem/.key da empresa para o Supabase Storage.
    """
    filename = os.path.basename(arquivo.filename)

    if filename not in ALLOWED_FILENAMES:
        raise HTTPException(
            status_code=400,
            detail=f"❌ Nome de arquivo inválido. Use: {', '.join(ALLOWED_FILENAMES)}"
        )

    try:
        file_content = await arquivo.read()

        # 🔒 Garante que o diretório no bucket existe antes de enviar
        await ensure_folder_exists(empresa_id)

        success = await upload_cert_file(
            empresa_id=empresa_id,
            filename=filename,
            file_bytes=file_content
        )

        if not success:
            raise HTTPException(status_code=500, detail="❌ Erro ao subir o certificado.")

        return JSONResponse(content={"message": f"✅ {filename} enviado com sucesso."})

    except Exception as e:
        logger.error(f"❌ Erro durante upload de certificado: {str(e)}")
        raise HTTPException(status_code=500, detail="❌ Falha ao processar o upload.")
