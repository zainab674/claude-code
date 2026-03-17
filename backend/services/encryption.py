"""
SSN encryption service using AES-256-GCM.
The SSN is never stored in plaintext — only the encrypted blob is saved.

Key derivation: PBKDF2-HMAC-SHA256 from SSN_ENCRYPTION_KEY env var.
Each SSN gets a unique salt (stored alongside ciphertext as base64).

Format stored in DB: "v1:base64(salt):base64(nonce):base64(ciphertext)"

Set SSN_ENCRYPTION_KEY in .env — at least 32 random characters.
If not set, SSNs are stored with a warning (not encrypted) so the system
still works in development without configuration.
"""
import os
import base64
import hashlib
import hmac
import secrets
import logging

logger = logging.getLogger(__name__)

SSN_KEY = os.getenv("SSN_ENCRYPTION_KEY", "")
_warned = False


def _derive_key(master_key: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from the master key + salt."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        master_key.encode("utf-8"),
        salt,
        iterations=100_000,
        dklen=32,
    )


def encrypt_ssn(ssn: str) -> str:
    """
    Encrypt an SSN. Returns a versioned encrypted string safe to store in DB.
    Returns "" if SSN is empty.
    """
    if not ssn:
        return ""

    # Normalize: remove dashes and spaces
    ssn_clean = ssn.replace("-", "").replace(" ", "").strip()
    if len(ssn_clean) != 9 or not ssn_clean.isdigit():
        raise ValueError("SSN must be 9 digits")

    if not SSN_KEY:
        global _warned
        if not _warned:
            logger.warning("SSN_ENCRYPTION_KEY not set — SSNs stored unencrypted (development only)")
            _warned = True
        return f"plain:{ssn_clean}"

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        logger.warning("cryptography package not installed — SSNs stored unencrypted")
        return f"plain:{ssn_clean}"

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)   # 96-bit nonce for GCM
    key = _derive_key(SSN_KEY, salt)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, ssn_clean.encode(), None)

    return ":".join([
        "v1",
        base64.b64encode(salt).decode(),
        base64.b64encode(nonce).decode(),
        base64.b64encode(ciphertext).decode(),
    ])


def decrypt_ssn(encrypted: str) -> str:
    """
    Decrypt an SSN. Returns the 9-digit SSN string.
    Returns "" if encrypted is empty.
    """
    if not encrypted:
        return ""

    if encrypted.startswith("plain:"):
        return encrypted[6:]

    parts = encrypted.split(":")
    if len(parts) != 4 or parts[0] != "v1":
        raise ValueError("Unknown SSN format")

    if not SSN_KEY:
        raise ValueError("SSN_ENCRYPTION_KEY not set — cannot decrypt")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise ImportError("Install cryptography: pip install cryptography")

    _, salt_b64, nonce_b64, ct_b64 = parts
    salt = base64.b64decode(salt_b64)
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ct_b64)

    key = _derive_key(SSN_KEY, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def mask_ssn(ssn: str) -> str:
    """Return masked version: ***-**-1234"""
    if len(ssn) == 9 and ssn.isdigit():
        return f"***-**-{ssn[-4:]}"
    return "***-**-****"


def get_last_four(encrypted: str) -> str:
    """Return last 4 digits of SSN without full decryption (stored separately in prod)."""
    try:
        ssn = decrypt_ssn(encrypted)
        return ssn[-4:] if len(ssn) >= 4 else "****"
    except Exception:
        return "****"
