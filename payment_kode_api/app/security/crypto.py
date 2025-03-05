from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization, hashes
import base64
from ..database.database import get_empresa_certificados  # 🔹 Certifique-se que a função tem esse nome correto


def get_private_key(empresa_id: str):
    """Busca a chave privada RSA da empresa no banco de dados."""
    certificados = get_empresa_certificados(empresa_id)  # 🔹 Nome da função corrigido
    if not certificados or not certificados.get("private_key_base64"):
        raise ValueError(f"Chave privada não encontrada para empresa {empresa_id}")
    
    private_key_pem = base64.b64decode(certificados["private_key_base64"])
    return serialization.load_pem_private_key(private_key_pem, password=None)


def get_public_key(empresa_id: str):
    """Busca a chave pública RSA da empresa no banco de dados."""
    certificados = get_empresa_certificados(empresa_id)  # 🔹 Nome da função corrigido
    if not certificados or not certificados.get("public_key_base64"):
        raise ValueError(f"Chave pública não encontrada para empresa  {empresa_id}")
    
    public_key_pem = base64.b64decode(certificados["public_key_base64"])
    return serialization.load_pem_public_key(public_key_pem)


def encrypt_card_data(empresa_id: str, card_data: dict) -> str:
    """Criptografa os dados do cartão com a chave pública da empresa."""
    public_key = get_public_key(empresa_id)
    plaintext = f"{card_data['card_number']}|{card_data['security_code']}|{card_data['expiration_month']}|{card_data['expiration_year']}"
    ciphertext = public_key.encrypt(
        plaintext.encode(),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.b64encode(ciphertext).decode()


def decrypt_card_data(empresa_id: str, encrypted_data: str) -> dict:
    """Descriptografa os dados do cartão usando a chave privada da empresa."""
    private_key = get_private_key(empresa_id)
    decrypted_bytes = private_key.decrypt(
        base64.b64decode(encrypted_data),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    decrypted_text = decrypted_bytes.decode()
    card_number, security_code, expiration_month, expiration_year = decrypted_text.split('|')
    return {
        "card_number": card_number,
        "security_code": security_code,
        "expiration_month": expiration_month,
        "expiration_year": expiration_year
    }
