import hashlib
import tempfile
import ssl
from typing import Tuple, Union


def write_temp_cert(cert_bytes: bytes, suffix: str) -> tempfile.NamedTemporaryFile:
    """
    Escreve certificados temporários em disco, usado para compatibilidade com bibliotecas que não aceitam bytes diretamente.
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb")
    temp_file.write(cert_bytes)
    temp_file.flush()
    return temp_file


def get_md5(content: bytes) -> str:
    """
    Gera o hash MD5 de um conteúdo (útil para debug e rastreamento de certificados).
    """
    return hashlib.md5(content).hexdigest()


def build_ssl_context_from_memory(
    cert_pem: Union[str, bytes],
    key_pem: Union[str, bytes],
    ca_pem: Union[str, bytes]
) -> ssl.SSLContext:
    """
    Cria um contexto SSL diretamente da memória (sem precisar salvar arquivos fixos no disco).
    Usa arquivos temporários apenas para cert/key pois o OpenSSL exige caminho para load_cert_chain().
    O CA é carregado diretamente via cadata.
    """
    ssl_ctx = ssl.create_default_context(cadata=ca_pem.decode() if isinstance(ca_pem, bytes) else ca_pem)

    # Criamos arquivos temporários para cert/key
    cert_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
    cert_temp.write(cert_pem if isinstance(cert_pem, bytes) else cert_pem.encode())
    cert_temp.flush()

    key_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="wb")
    key_temp.write(key_pem if isinstance(key_pem, bytes) else key_pem.encode())
    key_temp.flush()

    ssl_ctx.load_cert_chain(certfile=cert_temp.name, keyfile=key_temp.name)

    return ssl_ctx
