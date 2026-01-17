# app/api/auth.py
"""
Authentication API Routes
=========================

Endpoints for user authentication and API key management.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import logging

from app.auth.middleware import (
    User, LoginRequest, LoginResponse, APIKeyCreate, APIKeyResponse,
    create_jwt_token, hash_password, verify_password,
    generate_api_key, require_auth, require_admin, check_rate_limit
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================

class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=2)


class UserResponse(BaseModel):
    """User response (without sensitive data)"""
    id: str
    email: str
    name: str
    role: str
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str = Field(..., min_length=8)


class APIKeyListResponse(BaseModel):
    """API key list item (without full key)"""
    id: str
    name: str
    prefix: str
    permissions: List[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    use_count: int


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest, req: Request):
    """
    Register a new user account.
    
    First user automatically becomes admin.
    """
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        # Check if email exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1",
            request.email
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Check if this is the first user (make admin)
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        role = "admin" if count == 0 else "user"
        
        # Create user
        user_id = str(uuid.uuid4())
        password_hash = hash_password(request.password)
        
        row = await conn.fetchrow("""
            INSERT INTO users (id, email, password_hash, name, role)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, email, name, role, created_at
        """, user_id, request.email, password_hash, request.name, role)
    
    logger.info(f"User registered: {request.email} (role: {role})")
    
    return UserResponse(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        created_at=row["created_at"]
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, req: Request, _: None = Depends(check_rate_limit)):
    """
    Login with email and password.

    Returns JWT token for authentication.
    Rate limited to prevent brute force attacks.
    """
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, email, password_hash, name, role
            FROM users WHERE email = $1
        """, request.email)
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(request.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create user object
    user = User(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"]
    )
    
    # Generate token
    token = create_jwt_token(user)
    expires_in = 24 * 60 * 60  # 24 hours in seconds
    
    # Update last login
    async with metadata_store._pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login_at = NOW() WHERE id = $1",
            row["id"]
        )
    
    logger.info(f"User logged in: {request.email}")
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Get current user information"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, role, created_at FROM users WHERE id = $1",
            current_user.id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        created_at=row["created_at"]
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Change current user's password"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        # Verify current password
        row = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )
        
        if not row or not verify_password(request.current_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Update password
        new_hash = hash_password(request.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
            new_hash, current_user.id
        )
    
    logger.info(f"Password changed for user: {current_user.email}")
    
    return {"status": "success", "message": "Password changed successfully"}


# =============================================================================
# API Key Management
# =============================================================================

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: APIKeyCreate,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """
    Create a new API key.
    
    **Important**: The full key is only shown once. Store it securely!
    """
    metadata_store = req.app.state.metadata_store
    
    # Generate key
    key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    prefix = key[:12]  # sk_live_xxxx
    
    # Calculate expiration
    expires_at = None
    if request.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_days)
    
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, permissions, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, name, key_prefix, permissions, created_at, expires_at
        """, key_id, current_user.id, request.name, key_hash, prefix, 
            request.permissions, expires_at)
    
    logger.info(f"API key created: {request.name} by {current_user.email}")
    
    return APIKeyResponse(
        id=str(row["id"]),
        name=row["name"],
        key=key,  # Full key - only shown once!
        prefix=row["key_prefix"],
        permissions=row["permissions"],
        created_at=row["created_at"],
        expires_at=row["expires_at"]
    )


@router.get("/api-keys", response_model=List[APIKeyListResponse])
async def list_api_keys(
    req: Request,
    current_user: User = Depends(require_auth)
):
    """List all API keys for current user"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        if current_user.role == "admin":
            # Admins can see all keys
            rows = await conn.fetch("""
                SELECT id, name, key_prefix, permissions, created_at, 
                       expires_at, last_used_at, use_count
                FROM api_keys
                WHERE revoked_at IS NULL
                ORDER BY created_at DESC
            """)
        else:
            rows = await conn.fetch("""
                SELECT id, name, key_prefix, permissions, created_at,
                       expires_at, last_used_at, use_count
                FROM api_keys
                WHERE user_id = $1 AND revoked_at IS NULL
                ORDER BY created_at DESC
            """, current_user.id)
    
    return [
        APIKeyListResponse(
            id=str(row["id"]),
            name=row["name"],
            prefix=row["key_prefix"],
            permissions=row["permissions"] or [],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            use_count=row["use_count"] or 0
        )
        for row in rows
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Revoke an API key"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        # Check ownership (or admin)
        row = await conn.fetchrow(
            "SELECT user_id FROM api_keys WHERE id = $1",
            key_id
        )
        
        if not row:
            raise HTTPException(status_code=404, detail="API key not found")
        
        if str(row["user_id"]) != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized")
        
        await conn.execute(
            "UPDATE api_keys SET revoked_at = NOW() WHERE id = $1",
            key_id
        )
    
    logger.info(f"API key revoked: {key_id} by {current_user.email}")
    
    return {"status": "revoked", "key_id": key_id}


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    req: Request,
    current_user: User = Depends(require_admin)
):
    """List all users (admin only)"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, email, name, role, created_at
            FROM users
            ORDER BY created_at DESC
        """)
    
    return [
        UserResponse(
            id=str(row["id"]),
            email=row["email"],
            name=row["name"],
            role=row["role"],
            created_at=row["created_at"]
        )
        for row in rows
    ]


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str,
    req: Request,
    current_user: User = Depends(require_admin)
):
    """Update user role (admin only)"""
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET role = $1, updated_at = NOW() WHERE id = $2",
            role, user_id
        )
    
    return {"status": "updated", "user_id": user_id, "role": role}
