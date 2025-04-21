import uuid
import hashlib
import base64
import random
import string

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

def generate_random_string(length: int = 12) -> str:
    """
    Gera uma string aleatória segura para tokens ou identificadores temporários.
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def encode_base64(value: str) -> str:
    """
    Codifica uma string em Base64.
    """
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")

def decode_base64(value: str) -> str:
    """
    Decodifica uma string Base64 para texto normal.
    """
    return base64.b64decode(value.encode("utf-8")).decode("utf-8")
