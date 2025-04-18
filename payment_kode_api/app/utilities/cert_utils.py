import hashlib
import tempfile
from typing import Tuple


def write_temp_cert(cert_bytes: bytes, suffix: str) -> tempfile.NamedTemporaryFile:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb")
    temp_file.write(cert_bytes)
    temp_file.flush()
    return temp_file


def get_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()
