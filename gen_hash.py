
import logging
from app.auth.middleware import hash_password

# Configure minimal logging
logging.basicConfig(level=logging.ERROR)

def generate_hash():
    password = "admin123"
    hashed = hash_password(password)
    print(hashed)

if __name__ == "__main__":
    generate_hash()
