# app/auth/middleware.py
"""
Authentication Middleware
=========================

Supports multiple authentication methods:
1. API Key - For service-to-service calls
2. JWT Token - For user authentication
3. Session - For dashboard access

Usage:
    # API Key in header
    curl -H "X-API-Key: your-api-key" http://localhost:8000/api/...
    
    # JWT Bearer token
    curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/...
    
    # Login to get JWT
    curl -X POST http://localhost:8000/auth/login \
      -d '{"email": "user@example.com", "password": "xxx"}'
"""

from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import hashlib
import secrets
import jwt
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# JWT Settings
JWT_SECRET = settings.SECURITY_KEY or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# API Key header name
API_KEY_HEADER = "X-API-Key"

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


# =============================================================================
# Models
# =============================================================================

class User(BaseModel):
    """Authenticated user model"""
    id: str
    email: str
    name: str
    role: str = "user"  # user, admin, service
    permissions: list = []


class TokenData(BaseModel):
    """JWT token payload"""
    sub: str  # user id
    email: str
    name: str
    role: str
    exp: datetime
    iat: datetime


class LoginRequest(BaseModel):
    """Login request"""
    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class APIKeyCreate(BaseModel):
    """API key creation request"""
    name: str
    permissions: list = ["read", "write"]
    expires_days: Optional[int] = 365


class APIKeyResponse(BaseModel):
    """API key response"""
    id: str
    name: str
    key: str  # Only shown once on creation
    prefix: str  # First 8 chars for identification
    permissions: list
    created_at: datetime
    expires_at: Optional[datetime]


# =============================================================================
# JWT Functions
# =============================================================================

def create_jwt_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token for user"""
    if expires_delta is None:
        expires_delta = timedelta(hours=JWT_EXPIRATION_HOURS)
    
    now = datetime.utcnow()
    expire = now + expires_delta
    
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "iat": now,
        "exp": expire
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenData(**payload)
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


def hash_password(password: str) -> str:
    """Hash password with salt"""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        salt.encode(),
        100000
    ).hex()
    return f"{salt}:{hashed}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    try:
        salt, stored_hash = hashed.split(':')
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt.encode(),
            100000
        ).hex()
        return secrets.compare_digest(stored_hash, computed_hash)
    except Exception:
        return False


# =============================================================================
# API Key Functions
# =============================================================================

def generate_api_key() -> tuple[str, str]:
    """Generate API key and its hash"""
    # Format: sk_live_xxxxxxxxxxxxxxxxxxxx
    key = f"sk_live_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def hash_api_key(key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()


# =============================================================================
# Authentication Dependencies
# =============================================================================

async def get_api_key(
    api_key: Optional[str] = Depends(api_key_header),
    request: Request = None
) -> Optional[Dict[str, Any]]:
    """Validate API key from header"""
    if not api_key:
        return None
    
    # Hash the provided key
    key_hash = hash_api_key(api_key)
    
    # Look up in database
    try:
        metadata_store = request.app.state.metadata_store
        async with metadata_store._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM api_keys 
                WHERE key_hash = $1 
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND revoked_at IS NULL
            """, key_hash)
        
        if row:
            # Update last used
            async with metadata_store._pool.acquire() as conn:
                await conn.execute("""
                    UPDATE api_keys 
                    SET last_used_at = NOW(), use_count = use_count + 1
                    WHERE id = $1
                """, row["id"])
            
            return {
                "id": str(row["id"]),
                "name": row["name"],
                "permissions": row["permissions"],
                "user_id": str(row["user_id"]) if row["user_id"] else None
            }
    except Exception as e:
        logger.error(f"API key validation error: {e}")
    
    return None


async def get_jwt_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[User]:
    """Extract user from JWT bearer token"""
    if not credentials:
        return None
    
    token_data = decode_jwt_token(credentials.credentials)
    if not token_data:
        return None
    
    return User(
        id=token_data.sub,
        email=token_data.email,
        name=token_data.name,
        role=token_data.role
    )


async def get_current_user(
    request: Request,
    jwt_user: Optional[User] = Depends(get_jwt_user),
    api_key_data: Optional[Dict] = Depends(get_api_key)
) -> Optional[User]:
    """
    Get current authenticated user from JWT or API key.
    Returns None if not authenticated.
    """
    # JWT takes priority
    if jwt_user:
        return jwt_user
    
    # API key authentication
    if api_key_data:
        return User(
            id=api_key_data.get("user_id", "service"),
            email="api-key@service",
            name=api_key_data["name"],
            role="service",
            permissions=api_key_data.get("permissions", [])
        )
    
    return None


async def require_auth(
    user: Optional[User] = Depends(get_current_user)
) -> User:
    """Require authentication - raises 401 if not authenticated"""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def require_admin(
    user: User = Depends(require_auth)
) -> User:
    """Require admin role"""
    if user.role not in ("admin", "service"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


def require_permission(permission: str):
    """Dependency factory to require specific permission"""
    async def check_permission(user: User = Depends(require_auth)) -> User:
        if user.role == "admin":
            return user
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
        return user
    return check_permission


# =============================================================================
# Optional Authentication (for public endpoints with enhanced features)
# =============================================================================

async def optional_auth(
    user: Optional[User] = Depends(get_current_user)
) -> Optional[User]:
    """Optional authentication - returns None if not authenticated"""
    return user


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed"""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old requests
        if key in self.requests:
            self.requests[key] = [
                t for t in self.requests[key] if t > minute_ago
            ]
        else:
            self.requests[key] = []
        
        # Check limit
        if len(self.requests[key]) >= self.requests_per_minute:
            return False
        
        # Record request
        self.requests[key].append(now)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=60)


async def check_rate_limit(request: Request):
    """Rate limiting dependency"""
    # Use IP or API key as identifier
    client_ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get(API_KEY_HEADER, "")
    
    key = api_key[:8] if api_key else client_ip
    
    if not rate_limiter.is_allowed(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": "60"}
        )
