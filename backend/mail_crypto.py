"""Fernet-based password encryption for mail account credentials."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc::"
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        secret = os.environ.get("APP_SECRET", "dev-only-insecure-key-please-change")
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


def encrypt_text(value: str) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX):
        return value
    return _PREFIX + _get_fernet().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value
    try:
        return _get_fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, Exception):
        return ""
