import hashlib
import tempfile
import ssl
from typing import Union


def get_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def build_ssl_context_from_memory(
    cert_pem: Union[str, bytes],
    key_pem: Union[str, bytes],
    ca_pem: Union[str, bytes]
) -> ssl.SSLContext:
    """
    Cria um contexto SSL a partir de certificados e chave em memória.
    Gera arquivos temporários apenas para cert/key — o CA é carregado via cadata.
    """
    if isinstance(cert_pem, str):
        cert_pem = cert_pem.encode()
    if isinstance(key_pem, str):
        key_pem = key_pem.encode()
    if isinstance(ca_pem, str):
        ca_pem = ca_pem.encode()

    # Cria arquivos temporários (serão apagados com delete=True ao sair do processo)
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
    cert_file.write(cert_pem)
    cert_file.flush()

    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="wb")
    key_file.write(key_pem)
    key_file.flush()

    ssl_ctx = ssl.create_default_context(cadata=ca_pem.decode())
    ssl_ctx.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED

    return ssl_ctx
