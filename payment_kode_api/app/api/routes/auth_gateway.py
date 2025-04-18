from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from payment_kode_api.app.services.gateways.sicredi_client import get_access_token
from payment_kode_api.app.services.config_service import create_temp_cert_files
from payment_kode_api.app.utilities.logging_config import logger

router = APIRouter(prefix="/auth_gateway", tags=["Auth Gateway"])


@router.get("/sicredi_token")
async def obter_token_sicredi(
    empresa_id: str = Query(..., min_length=36, max_length=36, description="ID da empresa (UUID)")
):
    """
    Retorna o access_token da Sicredi para a empresa informada.
    Valida certificados e utiliza cache Redis se disponível.
    """
    try:
        logger.info(f"🔐 [Token Sicredi] Empresa: {empresa_id} — iniciando validação de certificados.")
        await create_temp_cert_files(empresa_id)

        logger.info(f"📡 [Token Sicredi] Solicitando token...")
        token = await get_access_token(empresa_id)

        logger.success(f"✅ [Token Sicredi] Token recuperado com sucesso para empresa {empresa_id}.")
        return JSONResponse(content={
            "empresa_id": empresa_id,
            "access_token": token,
            "message": "✅ Token obtido com sucesso"
        })

    except HTTPException as http_exc:
        raise http_exc

    except Exception as e:
        logger.error(f"❌ [Token Sicredi] Erro inesperado: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro ao obter token da Sicredi")
