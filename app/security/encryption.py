# app/security/encryption.py
from cryptography.fernet import Fernet
import logging
import base64
from app.config import settings

logger = logging.getLogger(__name__)

class EncryptionService:
    """Service to encrypt and decrypt sensitive data"""
    
    def __init__(self, key: str = None):
        # Prefer provided key, fallback to settings
        self.key = key or getattr(settings, "SECURITY_KEY", None)

        if not self.key:
            raise ValueError(
                "SECURITY_KEY environment variable is required. "
                "Generate one with: openssl rand -base64 32"
            )

        try:
            self.cipher_suite = Fernet(self.key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise

    def encrypt(self, plain_text: str) -> str:
        """Encrypt a string"""
        if not plain_text:
            return None
        try:
            encrypted_bytes = self.cipher_suite.encrypt(plain_text.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt a string"""
        if not encrypted_text:
            return None
        try:
            decrypted_bytes = self.cipher_suite.decrypt(encrypted_text.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
