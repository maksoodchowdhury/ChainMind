"""Secure JSON persistence helpers with optional at-rest encryption."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path


def _encryption_enabled() -> bool:
    return os.getenv("DATA_ENCRYPTION_ENABLED", "false").strip().lower() == "true"


def _encryption_key() -> str | None:
    return os.getenv("DATA_ENCRYPTION_KEY")


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt(text: str) -> str:
    key = _encryption_key()
    if not key:
        raise RuntimeError("DATA_ENCRYPTION_ENABLED=true but DATA_ENCRYPTION_KEY is not configured")
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except Exception as e:
        raise RuntimeError("cryptography package is required for at-rest encryption") from e
    cipher = Fernet(_derive_fernet_key(key))
    return cipher.encrypt(text.encode("utf-8")).decode("utf-8")


def _decrypt(token: str) -> str:
    key = _encryption_key()
    if not key:
        raise RuntimeError("Encrypted store cannot be read: DATA_ENCRYPTION_KEY is missing")
    from cryptography.fernet import Fernet  # type: ignore

    cipher = Fernet(_derive_fernet_key(key))
    return cipher.decrypt(token.encode("utf-8")).decode("utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        raw = path.read_text()
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("__encrypted__") is True:
            plaintext = _decrypt(parsed.get("payload", ""))
            return json.loads(plaintext)
        return parsed
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _encryption_enabled():
        payload = {
            "__encrypted__": True,
            "algorithm": "fernet-sha256-derived",
            "payload": _encrypt(json.dumps(data, separators=(",", ":"))),
        }
        path.write_text(json.dumps(payload, indent=2))
        return
    path.write_text(json.dumps(data, indent=2))
