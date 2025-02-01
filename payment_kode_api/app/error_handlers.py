from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.utilities.logging_config import logger

def add_error_handlers(app):
    """
    Registra handlers de erro na aplicação FastAPI.
    """
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.error(f"HTTPException: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled Exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"message": "Ocorreu um erro interno no servidor."},
        )
