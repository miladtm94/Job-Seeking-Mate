"""Encrypted local credential store for job-board platforms.

Credentials are encrypted with Fernet (AES-128-CBC + HMAC) before being
written to disk.  The symmetric key lives in ``data/.credential_key`` (mode
0o600) and is auto-generated on first use.  Both files are gitignored.

Only the three supported platforms (indeed / linkedin / seek) are accepted.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_DATA_DIR  = Path(__file__).resolve().parents[4] / "data"
_KEY_PATH  = _DATA_DIR / ".credential_key"
_CRED_PATH = _DATA_DIR / "saved_credentials.enc"

SUPPORTED_PLATFORMS = {"indeed", "linkedin", "seek"}


def _fernet() -> Fernet:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _KEY_PATH.exists():
        _KEY_PATH.write_bytes(Fernet.generate_key())
        os.chmod(_KEY_PATH, 0o600)
        logger.info("Generated new credential key at %s", _KEY_PATH)
    return Fernet(_KEY_PATH.read_bytes())


def _load_all() -> dict:
    if not _CRED_PATH.exists():
        return {}
    try:
        raw = _fernet().decrypt(_CRED_PATH.read_bytes())
        return json.loads(raw.decode())
    except (InvalidToken, Exception) as exc:
        logger.warning("Could not decrypt credential store: %s", exc)
        return {}


def _save_all(data: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _fernet().encrypt(json.dumps(data).encode())
    _CRED_PATH.write_bytes(encrypted)
    os.chmod(_CRED_PATH, 0o600)


def load(platform: str) -> dict | None:
    """Return {email, password} for *platform*, or None if not saved."""
    return _load_all().get(platform.lower())


def save(platform: str, email: str, password: str) -> None:
    """Encrypt and persist credentials for *platform*."""
    platform = platform.lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform!r}")
    data = _load_all()
    data[platform] = {"email": email, "password": password}
    _save_all(data)
    logger.info("Saved credentials for %s", platform)


def delete(platform: str) -> None:
    """Remove saved credentials for *platform*."""
    data = _load_all()
    data.pop(platform.lower(), None)
    _save_all(data)


def list_saved() -> list[str]:
    """Return list of platform names that have saved credentials."""
    return list(_load_all().keys())
