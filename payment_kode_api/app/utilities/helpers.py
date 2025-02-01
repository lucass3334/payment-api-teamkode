import uuid
import hashlib

def generate_transaction_id() -> str:
    """
    Gera um ID único para transações.
    """
    return str(uuid.uuid4())

def hash_string(value: str) -> str:
    """
    Retorna o hash SHA-256 de uma string.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
