"""
Sensitive configuration encryption/decryption utility.

Uses Fernet (symmetric encryption via the `cryptography` package).
The encryption key is stored in a separate file (`.config_key`) that should NOT
be committed to version control. If no key file exists, one is auto-generated
on first use.

Usage:
    ciphertext = encrypt_sensitive("my-api-key")
    plaintext = decrypt_sensitive(ciphertext)
"""
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

# Store the key file alongside .env (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = PROJECT_ROOT / ".config_key"


def _get_or_create_key() -> bytes:
    """Load the encryption key from file, or create one if it doesn't exist."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()

    key = Fernet.generate_key()
    # Write with restrictive permissions
    KEY_FILE.write_bytes(key)
    # Try to set read-only on Unix
    try:
        KEY_FILE.chmod(0o600)
    except Exception:
        pass
    return key


def encrypt_sensitive(value: str) -> str:
    """Encrypt a sensitive string value. Returns a base64-encoded ciphertext string."""
    if not value:
        return ""
    key = _get_or_create_key()
    f = Fernet(key)
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_sensitive(ciphertext: str) -> str:
    """Decrypt a previously encrypted string. Returns the original plaintext.

    If decryption fails (e.g., wrong key or corrupted data), returns the input
    as-is for backward compatibility with unencrypted values.
    """
    if not ciphertext:
        return ""
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Return as-is for backward compatibility (unencrypted values)
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Check if a value is already encrypted (Fernet tokens are base64 with specific format)."""
    if not value:
        return False
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        f.decrypt(value.encode("utf-8"))
        return True
    except (InvalidToken, Exception):
        return False
