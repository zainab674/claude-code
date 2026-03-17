import os
import logging
from cryptography.fernet import Fernet
from config import settings

logger = logging.getLogger(__name__)

# Use a default key for development if not provided, but warn loudly
DEFAULT_DEV_KEY = Fernet.generate_key().decode()
ENCRYPTION_KEY = settings.SSN_ENCRYPTION_KEY or os.getenv("SSN_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    logger.warning("SSN_ENCRYPTION_KEY not set! Using a temporary development key. DATA WILL NOT BE RECOVERABLE AFTER RESTART!")
    ENCRYPTION_KEY = DEFAULT_DEV_KEY

try:
    _fernet = Fernet(ENCRYPTION_KEY.encode())
except Exception as e:
    logger.error(f"Invalid SSN_ENCRYPTION_KEY: {e}. Generating a new one for this session.")
    _fernet = Fernet(Fernet.generate_key())

def encrypt_data(data: str) -> str:
    """Encrypt a string and return a base64 string."""
    if not data:
        return data
    return _fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt a base64 string and return the original string."""
    if not encrypted_data:
        return encrypted_data
    try:
        return _fernet.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return "[DECRYPTION_FAILED]"
