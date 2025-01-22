from loguru import logger
import sys
import os

# Remove a configuração padrão
logger.remove()

# Configuração para logs no console
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# Configuração para logs em arquivo rotativo
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)  # Cria o diretório "logs" se não existir
logger.add(
    os.path.join(LOG_DIR, "app.log"),
    rotation="10 MB",  # Roda o arquivo quando atinge 10 MB
    retention="10 days",  # Mantém os logs por 10 dias
    compression="zip",  # Comprime os logs antigos
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
)

# Exemplo de uso (pode ser removido após os testes)
if __name__ == "__main__":
    logger.info("Informação geral de inicialização")
    logger.warning("Aviso sobre algo importante")
    logger.error("Erro ao executar a aplicação")
