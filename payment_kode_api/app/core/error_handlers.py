from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from payment_kode_api.app.utilities.logging_config import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

def add_error_handlers(app):
    """
    Registra handlers de erro na aplicação FastAPI.
    """
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.error(f"HTTPException: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "HTTPException", "message": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.error(f"StarletteHTTPException: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "StarletteHTTPException", "message": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled Exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "InternalServerError", "message": "Ocorreu um erro interno no servidor."},
        )
