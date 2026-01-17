# app/api/notifications.py
"""
Notification Management API
===========================

Manage notification preferences and test notifications.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, HttpUrl
from typing import Optional
import logging
import secrets

from app.auth.middleware import User, require_auth
from app.notifications.email_service import email_service

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================

class NotificationPreferences(BaseModel):
    """User notification preferences"""
    email_import_complete: bool = True
    email_import_failed: bool = True
    email_weekly_summary: bool = False
    
    webhook_url: Optional[str] = None
    webhook_enabled: bool = False


class WebhookTest(BaseModel):
    """Webhook test request"""
    url: str


class EmailTest(BaseModel):
    """Email test request"""
    to_email: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/preferences", response_model=NotificationPreferences)
async def get_preferences(
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Get current user's notification preferences"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT email_import_complete, email_import_failed, 
                   email_weekly_summary, webhook_url, webhook_enabled
            FROM notification_preferences
            WHERE user_id = $1
        """, current_user.id)
    
    if not row:
        # Return defaults
        return NotificationPreferences()
    
    return NotificationPreferences(
        email_import_complete=row["email_import_complete"],
        email_import_failed=row["email_import_failed"],
        email_weekly_summary=row["email_weekly_summary"],
        webhook_url=row["webhook_url"],
        webhook_enabled=row["webhook_enabled"]
    )


@router.put("/preferences", response_model=NotificationPreferences)
async def update_preferences(
    prefs: NotificationPreferences,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Update notification preferences"""
    metadata_store = req.app.state.metadata_store
    
    # Generate webhook secret if enabling webhook
    webhook_secret = None
    if prefs.webhook_enabled and prefs.webhook_url:
        webhook_secret = secrets.token_hex(32)
    
    async with metadata_store._pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO notification_preferences 
                (user_id, email_import_complete, email_import_failed, 
                 email_weekly_summary, webhook_url, webhook_enabled, webhook_secret)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id) DO UPDATE SET
                email_import_complete = EXCLUDED.email_import_complete,
                email_import_failed = EXCLUDED.email_import_failed,
                email_weekly_summary = EXCLUDED.email_weekly_summary,
                webhook_url = EXCLUDED.webhook_url,
                webhook_enabled = EXCLUDED.webhook_enabled,
                webhook_secret = COALESCE(EXCLUDED.webhook_secret, notification_preferences.webhook_secret),
                updated_at = NOW()
        """, current_user.id, prefs.email_import_complete, prefs.email_import_failed,
            prefs.email_weekly_summary, prefs.webhook_url, prefs.webhook_enabled, 
            webhook_secret)
    
    logger.info(f"Updated notification preferences for user {current_user.id}")
    
    return prefs


@router.post("/test/email")
async def test_email_notification(
    test: EmailTest,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Send a test email notification"""
    success = await email_service.send_import_complete(
        to_email=test.to_email,
        job_id="test-job-123",
        folder_name="Test Folder",
        files_processed=42,
        chunks_created=156,
        files_failed=2,
        duration_seconds=125
    )
    
    if success:
        return {"status": "sent", "to_email": test.to_email}
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send test email. Check email configuration."
        )


@router.post("/test/webhook")
async def test_webhook_notification(
    test: WebhookTest,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Send a test webhook notification"""
    import httpx
    
    payload = {
        "event": "test",
        "timestamp": "2024-01-01T12:00:00Z",
        "data": {
            "message": "This is a test webhook from SharePoint RAG",
            "user_id": current_user.id
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                test.url,
                json=payload,
                timeout=10.0
            )
        
        return {
            "status": "sent",
            "webhook_url": test.url,
            "response_status": response.status_code,
            "response_body": response.text[:500]
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Webhook test failed: {str(e)}"
        )


@router.get("/webhook-secret")
async def get_webhook_secret(
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Get current webhook secret for signature verification"""
    metadata_store = req.app.state.metadata_store
    
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT webhook_secret FROM notification_preferences
            WHERE user_id = $1
        """, current_user.id)
    
    if not row or not row["webhook_secret"]:
        raise HTTPException(status_code=404, detail="No webhook configured")
    
    return {"webhook_secret": row["webhook_secret"]}


@router.post("/webhook-secret/regenerate")
async def regenerate_webhook_secret(
    req: Request,
    current_user: User = Depends(require_auth)
):
    """Regenerate webhook secret"""
    metadata_store = req.app.state.metadata_store
    new_secret = secrets.token_hex(32)
    
    async with metadata_store._pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE notification_preferences 
            SET webhook_secret = $2, updated_at = NOW()
            WHERE user_id = $1
        """, current_user.id, new_secret)
    
    return {"webhook_secret": new_secret}
