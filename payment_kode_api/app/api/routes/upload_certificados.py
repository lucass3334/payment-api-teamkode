from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from payment_kode_api.app.database.supabase_storage import (
    upload_cert_file,
    ensure_folder_exists,
    download_cert_file,
    SUPABASE_BUCKET,
)
from payment_kode_api.app.utilities.logging_config import logger
import os
import hashlib

router = APIRouter(prefix="/certificados", tags=["Certificados"])

ALLOWED_FILENAMES = {"sicredi-cert.pem", "sicredi-key.key", "sicredi-ca.pem"}


@router.post("/upload")
async def upload_certificado(
    empresa_id: str = Form(...),
    arquivo: UploadFile = File(...)
):
    """
    Upload seguro de um certificado .pem/.key para o Supabase Storage.
    """
    filename = os.path.basename(arquivo.filename.strip().lower())

    if filename not in ALLOWED_FILENAMES:
        raise HTTPException(
            status_code=400,
            detail=f"❌ Nome de arquivo inválido. Use apenas: {', '.join(sorted(ALLOWED_FILENAMES))}"
        )

    try:
        content = await arquivo.read()

        if not content or len(content.strip()) < 50 or b"-----BEGIN" not in content:
            raise HTTPException(status_code=400, detail="❌ Conteúdo do certificado inválido ou vazio.")

        await ensure_folder_exists(empresa_id=empresa_id, bucket=SUPABASE_BUCKET)

        success = await upload_cert_file(
            empresa_id=empresa_id,
            filename=filename,
            file_bytes=content
        )

        if not success:
            raise HTTPException(status_code=500, detail="❌ Erro ao subir o certificado.")

        logger.info(f"✅ Certificado {filename} enviado com sucesso para empresa {empresa_id}.")
        return JSONResponse(content={"message": f"✅ {filename} enviado com sucesso."})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro inesperado no upload do certificado {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="❌ Falha ao processar o upload.")


@router.get("/validate")
async def validar_certificados(empresa_id: str):
    """
    Valida se todos os certificados (cert, key, ca) estão presentes no bucket
    e possuem conteúdo válido diretamente da memória.
    """
    missing_or_invalid = []

    for filename in sorted(ALLOWED_FILENAMES):
        try:
            logger.info(f"🔍 Validando {filename} para empresa {empresa_id}...")
            content = await download_cert_file(empresa_id=empresa_id, filename=filename)

            if not content or len(content.strip()) < 50 or b"-----BEGIN" not in content:
                logger.warning(f"⚠️ {filename} inválido ou incompleto.")
                missing_or_invalid.append(filename)
                continue

            hash_digest = hashlib.md5(content).hexdigest()
            logger.info(f"📄 {filename} válido (md5: {hash_digest})")

        except Exception as e:
            logger.warning(f"⚠️ Erro ao validar {filename} da empresa {empresa_id}: {str(e)}")
            missing_or_invalid.append(filename)

    if missing_or_invalid:
        return JSONResponse(
            status_code=400,
            content={
                "status": "invalid",
                "empresa_id": empresa_id,
                "missing_or_invalid": missing_or_invalid
            }
        )

    return JSONResponse(
        content={
            "status": "ok",
            "empresa_id": empresa_id,
            "message": "✅ Todos os certificados estão presentes e válidos."
        }
    )
