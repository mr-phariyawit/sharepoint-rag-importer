
import unittest
from app.security.encryption import EncryptionService
from app.config import settings

class TestEncryptionService(unittest.TestCase):
    def setUp(self):
        # Ensure we have a key for testing
        if not settings.SECURITY_KEY:
            # Generate a temporary key for testing if none is set
            from cryptography.fernet import Fernet
            settings.SECURITY_KEY = Fernet.generate_key().decode()
        self.service = EncryptionService()

    def test_encrypt_decrypt(self):
        secret = "super_secret_value"
        encrypted = self.service.encrypt(secret)
        self.assertNotEqual(secret, encrypted)
        
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(secret, decrypted)

    def test_decrypt_invalid(self):
        with self.assertRaises(Exception):
            self.service.decrypt("invalid_token")

if __name__ == '__main__':
    unittest.main()
