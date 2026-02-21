"""대칭 키 암호화 (Fernet) - 브로커 API 키 등 민감 정보 보호."""

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _derive_key(secret: str) -> bytes:
    """JWT_SECRET_KEY 기반 Fernet 키 생성 (32-byte → base64)."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key(settings.JWT_SECRET_KEY))


def encrypt(plaintext: str) -> str:
    """평문 → 암호문 (base64 문자열)."""
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """암호문 → 평문."""
    if not ciphertext:
        return ""
    return _fernet.decrypt(ciphertext.encode()).decode()


def mask_value(value: str) -> str:
    """표시용 마스킹: 앞 4자리 + **** + 뒤 4자리."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]
