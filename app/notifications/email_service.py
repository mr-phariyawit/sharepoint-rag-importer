# app/notifications/email_service.py
"""
Email Notification Service
==========================

Send email notifications for import events.

Supports multiple email providers:
- SMTP (Gmail, Outlook, custom)
- SendGrid
- AWS SES
- Mailgun

Usage:
    from app.notifications.email_service import email_service
    
    await email_service.send_import_complete(
        to_email="user@example.com",
        job_id="xxx",
        stats={"files": 100, "chunks": 500}
    )
"""

import os
import asyncio
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from abc import ABC, abstractmethod
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class EmailConfig:
    """Email configuration"""
    provider: str = "smtp"  # smtp, sendgrid, ses, mailgun
    
    # SMTP settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    
    # API providers
    api_key: str = ""
    api_endpoint: str = ""
    
    # Sender info
    from_email: str = "noreply@sharepoint-rag.local"
    from_name: str = "SharePoint RAG"
    
    # App settings
    app_url: str = "http://localhost:8000"


def get_email_config() -> EmailConfig:
    """Load email config from environment"""
    return EmailConfig(
        provider=os.getenv("EMAIL_PROVIDER", "smtp"),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        api_key=os.getenv("EMAIL_API_KEY", ""),
        from_email=os.getenv("EMAIL_FROM", "noreply@sharepoint-rag.local"),
        from_name=os.getenv("EMAIL_FROM_NAME", "SharePoint RAG"),
        app_url=os.getenv("APP_URL", "http://localhost:8000")
    )


# =============================================================================
# Email Templates
# =============================================================================

TEMPLATES = {
    "import_complete": {
        "subject": "✅ Import Complete: {folder_name}",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 12px; color: #666; }}
        .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; margin-top: 20px; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">✅ Import Complete!</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">{folder_name}</p>
        </div>
        <div class="content">
            <p>Good news! Your SharePoint folder import has completed successfully.</p>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{files_processed}</div>
                    <div class="stat-label">Files Processed</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{chunks_created}</div>
                    <div class="stat-label">Chunks Created</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{files_failed}</div>
                    <div class="stat-label">Files Failed</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{duration}</div>
                    <div class="stat-label">Duration</div>
                </div>
            </div>
            
            <p>Your documents are now indexed and ready for querying.</p>
            
            <center>
                <a href="{app_url}/dashboard" class="button">Open Dashboard</a>
            </center>
        </div>
        <div class="footer">
            <p>SharePoint RAG Importer</p>
            <p>Job ID: {job_id}</p>
        </div>
    </div>
</body>
</html>
        """,
        "text": """
Import Complete: {folder_name}

Your SharePoint folder import has completed successfully.

Stats:
- Files Processed: {files_processed}
- Chunks Created: {chunks_created}
- Files Failed: {files_failed}
- Duration: {duration}

Open Dashboard: {app_url}/dashboard

Job ID: {job_id}
        """
    },
    
    "import_failed": {
        "subject": "❌ Import Failed: {folder_name}",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .error-box {{ background: #fff5f5; border: 1px solid #e74c3c; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .button {{ display: inline-block; background: #e74c3c; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; margin-top: 20px; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">❌ Import Failed</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">{folder_name}</p>
        </div>
        <div class="content">
            <p>Unfortunately, your SharePoint folder import encountered an error.</p>
            
            <div class="error-box">
                <strong>Error:</strong><br>
                {error_message}
            </div>
            
            <p>Partial results:</p>
            <ul>
                <li>Files Found: {files_found}</li>
                <li>Files Processed: {files_processed}</li>
                <li>Files Failed: {files_failed}</li>
            </ul>
            
            <center>
                <a href="{app_url}/dashboard" class="button">View Details</a>
            </center>
        </div>
        <div class="footer">
            <p>SharePoint RAG Importer</p>
            <p>Job ID: {job_id}</p>
        </div>
    </div>
</body>
</html>
        """,
        "text": """
Import Failed: {folder_name}

Your SharePoint folder import encountered an error.

Error: {error_message}

Partial results:
- Files Found: {files_found}
- Files Processed: {files_processed}
- Files Failed: {files_failed}

View Details: {app_url}/dashboard

Job ID: {job_id}
        """
    },
    
    "weekly_summary": {
        "subject": "📊 Weekly RAG Summary",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 12px; color: #666; }}
        .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; margin-top: 20px; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">📊 Weekly Summary</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">{date_range}</p>
        </div>
        <div class="content">
            <p>Here's your weekly RAG system summary:</p>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total_queries}</div>
                    <div class="stat-label">Queries</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{new_documents}</div>
                    <div class="stat-label">New Documents</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{total_vectors}</div>
                    <div class="stat-label">Total Vectors</div>
                </div>
            </div>
            
            <h3>Top Queries This Week:</h3>
            <ol>
                {top_queries}
            </ol>
            
            <center>
                <a href="{app_url}/dashboard" class="button">View Full Report</a>
            </center>
        </div>
        <div class="footer">
            <p>SharePoint RAG Importer</p>
        </div>
    </div>
</body>
</html>
        """,
        "text": """
Weekly RAG Summary - {date_range}

Stats:
- Total Queries: {total_queries}
- New Documents: {new_documents}
- Total Vectors: {total_vectors}

View Full Report: {app_url}/dashboard
        """
    }
}


# =============================================================================
# Email Providers
# =============================================================================

class EmailProvider(ABC):
    """Base email provider"""
    
    @abstractmethod
    async def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        pass


class SMTPProvider(EmailProvider):
    """SMTP email provider"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    async def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.config.from_name} <{self.config.from_email}>"
            msg['To'] = to_email
            
            # Attach text and HTML parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send via SMTP
            def send_sync():
                with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                    if self.config.smtp_use_tls:
                        server.starttls()
                    if self.config.smtp_user and self.config.smtp_password:
                        server.login(self.config.smtp_user, self.config.smtp_password)
                    server.send_message(msg)
            
            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_sync)
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False


class SendGridProvider(EmailProvider):
    """SendGrid email provider"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.api_url = "https://api.sendgrid.com/v3/mail/send"
    
    async def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        try:
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.config.from_email, "name": self.config.from_name},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_content}
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
            
            logger.info(f"Email sent via SendGrid to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False


# =============================================================================
# Email Service
# =============================================================================

class EmailService:
    """Main email service"""
    
    def __init__(self, config: Optional[EmailConfig] = None):
        self.config = config or get_email_config()
        self.provider = self._get_provider()
    
    def _get_provider(self) -> EmailProvider:
        """Get email provider based on config"""
        if self.config.provider == "sendgrid":
            return SendGridProvider(self.config)
        else:
            return SMTPProvider(self.config)
    
    def _render_template(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> tuple[str, str, str]:
        """Render email template"""
        template = TEMPLATES.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        
        # Add app_url to context
        context["app_url"] = self.config.app_url
        
        subject = template["subject"].format(**context)
        html = template["html"].format(**context)
        text = template["text"].format(**context)
        
        return subject, html, text
    
    async def send_email(
        self,
        to_email: str,
        template_name: str,
        context: Dict[str, Any]
    ) -> bool:
        """Send templated email"""
        try:
            subject, html, text = self._render_template(template_name, context)
            return await self.provider.send(to_email, subject, html, text)
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def send_import_complete(
        self,
        to_email: str,
        job_id: str,
        folder_name: str,
        files_processed: int,
        chunks_created: int,
        files_failed: int,
        duration_seconds: int
    ) -> bool:
        """Send import complete notification"""
        # Format duration
        if duration_seconds < 60:
            duration = f"{duration_seconds}s"
        elif duration_seconds < 3600:
            duration = f"{duration_seconds // 60}m {duration_seconds % 60}s"
        else:
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            duration = f"{hours}h {minutes}m"
        
        return await self.send_email(to_email, "import_complete", {
            "job_id": job_id,
            "folder_name": folder_name,
            "files_processed": files_processed,
            "chunks_created": chunks_created,
            "files_failed": files_failed,
            "duration": duration
        })
    
    async def send_import_failed(
        self,
        to_email: str,
        job_id: str,
        folder_name: str,
        error_message: str,
        files_found: int = 0,
        files_processed: int = 0,
        files_failed: int = 0
    ) -> bool:
        """Send import failed notification"""
        return await self.send_email(to_email, "import_failed", {
            "job_id": job_id,
            "folder_name": folder_name,
            "error_message": error_message,
            "files_found": files_found,
            "files_processed": files_processed,
            "files_failed": files_failed
        })
    
    async def send_weekly_summary(
        self,
        to_email: str,
        date_range: str,
        total_queries: int,
        new_documents: int,
        total_vectors: int,
        top_queries: List[str]
    ) -> bool:
        """Send weekly summary"""
        top_queries_html = "\n".join(f"<li>{q}</li>" for q in top_queries[:5])
        
        return await self.send_email(to_email, "weekly_summary", {
            "date_range": date_range,
            "total_queries": total_queries,
            "new_documents": new_documents,
            "total_vectors": total_vectors,
            "top_queries": top_queries_html
        })


# Global email service instance
email_service = EmailService()


# =============================================================================
# Notification Helper Functions
# =============================================================================

async def notify_import_complete(
    metadata_store,
    job_id: str,
    user_id: Optional[str] = None
):
    """Send notification when import completes"""
    try:
        # Get job details
        job = await metadata_store.get_import_job(job_id)
        if not job:
            return
        
        # Get user email if user_id provided
        if user_id:
            async with metadata_store._pool.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT email FROM users WHERE id = $1",
                    user_id
                )
                
                if user:
                    # Check notification preferences
                    prefs = await conn.fetchrow(
                        "SELECT * FROM notification_preferences WHERE user_id = $1",
                        user_id
                    )
                    
                    should_notify = not prefs or prefs.get("email_import_complete", True)
                    
                    if should_notify:
                        # Calculate duration
                        if job.get("started_at") and job.get("completed_at"):
                            duration = int((job["completed_at"] - job["started_at"]).total_seconds())
                        else:
                            duration = 0
                        
                        if job["status"] == "completed":
                            await email_service.send_import_complete(
                                to_email=user["email"],
                                job_id=job_id,
                                folder_name=job.get("folder_name", job.get("folder_url", "Unknown")),
                                files_processed=job.get("files_processed", 0),
                                chunks_created=job.get("total_chunks_created", 0),
                                files_failed=job.get("files_failed", 0),
                                duration_seconds=duration
                            )
                        elif job["status"] == "failed":
                            error_log = job.get("error_log", [])
                            error_msg = error_log[0].get("error", "Unknown error") if error_log else "Unknown error"
                            
                            await email_service.send_import_failed(
                                to_email=user["email"],
                                job_id=job_id,
                                folder_name=job.get("folder_name", job.get("folder_url", "Unknown")),
                                error_message=error_msg,
                                files_found=job.get("total_files_found", 0),
                                files_processed=job.get("files_processed", 0),
                                files_failed=job.get("files_failed", 0)
                            )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
