from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..database.database import get_empresa_by_token
from ..utilities.logging_config import logger

security = HTTPBearer()

def validate_access_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Valida o access_token enviado no header Authorization."""
    token = credentials.credentials
    empresa = get_empresa_by_token(token)
    if not empresa:
        logger.warning(f"Tentativa de acesso com token inválido: {token}")
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")
    
    logger.info(f"Access token validado com sucesso para empresa: {empresa['empresa_id']}")
    return empresa
