# app/api/webhooks.py
"""
SharePoint Webhook API
======================

Handle real-time notifications from SharePoint when files change.

SharePoint webhooks work as follows:
1. Register a webhook subscription for a list/library
2. SharePoint sends validation request (must respond within 5 seconds)
3. SharePoint sends notifications when items change
4. We process the changes asynchronously

Microsoft Graph Change Notifications:
https://docs.microsoft.com/en-us/graph/webhooks
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import asyncio

from app.config import settings
from app.sharepoint.client import SharePointClient
from app.auth.middleware import require_auth, User

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================

class WebhookSubscription(BaseModel):
    """Webhook subscription model"""
    id: Optional[str] = None
    connection_id: str
    resource: str  # e.g., /drives/{drive-id}/root
    change_type: str = "updated"  # created, updated, deleted
    notification_url: str
    expiration_datetime: Optional[datetime] = None
    client_state: Optional[str] = None


class WebhookNotification(BaseModel):
    """Incoming webhook notification from SharePoint"""
    subscription_id: str = Field(alias="subscriptionId")
    subscription_expiration_datetime: datetime = Field(alias="subscriptionExpirationDateTime")
    change_type: str = Field(alias="changeType")
    resource: str
    resource_data: Optional[Dict] = Field(None, alias="resourceData")
    client_state: Optional[str] = Field(None, alias="clientState")
    tenant_id: str = Field(alias="tenantId")


class WebhookValidation(BaseModel):
    """Webhook validation response"""
    validation_token: str


class SubscriptionRequest(BaseModel):
    """Request to create a webhook subscription"""
    connection_id: str
    drive_id: str
    folder_path: Optional[str] = "/"
    
    
class SubscriptionResponse(BaseModel):
    """Webhook subscription response"""
    id: str
    resource: str
    expiration: datetime
    status: str


# =============================================================================
# Webhook Endpoints
# =============================================================================

@router.post("/subscribe", response_model=SubscriptionResponse)
async def create_subscription(
    request: SubscriptionRequest,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """
    Create a webhook subscription for a SharePoint drive/folder.
    
    This will register with Microsoft Graph to receive notifications
    when files in the folder are created, updated, or deleted.
    """
    metadata_store = req.app.state.metadata_store
    
    # Get connection
    connection = await metadata_store.get_connection(request.connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Create SharePoint client
    client = SharePointClient(
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        client_secret=connection["client_secret_encrypted"]
    )
    
    try:
        await client.authenticate()
        
        # Build resource path
        if request.folder_path and request.folder_path != "/":
            resource = f"/drives/{request.drive_id}/root:/{request.folder_path.strip('/')}"
        else:
            resource = f"/drives/{request.drive_id}/root"
        
        # Generate client state for validation
        client_state = hashlib.sha256(
            f"{request.connection_id}:{settings.ENCRYPTION_KEY or 'default'}".encode()
        ).hexdigest()[:32]
        
        # Get the webhook URL (this server)
        base_url = str(req.base_url).rstrip('/')
        notification_url = f"{base_url}/api/webhooks/notify"
        
        # Create subscription via Graph API
        subscription = await create_graph_subscription(
            client=client,
            resource=resource,
            notification_url=notification_url,
            client_state=client_state,
            expiration_hours=4230  # Max ~176 days for drive items
        )
        
        # Store subscription in database
        await store_subscription(
            metadata_store,
            subscription_id=subscription["id"],
            connection_id=request.connection_id,
            resource=resource,
            expiration=subscription["expirationDateTime"],
            client_state=client_state
        )
        
        await client.close()
        
        return SubscriptionResponse(
            id=subscription["id"],
            resource=resource,
            expiration=datetime.fromisoformat(subscription["expirationDateTime"].replace("Z", "+00:00")),
            status="active"
        )
        
    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notify")
async def receive_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: Optional[str] = Query(None)
):
    """
    Receive webhook notifications from SharePoint.
    
    This endpoint handles two types of requests:
    1. Validation: SharePoint sends validationToken query param
    2. Notification: SharePoint sends JSON body with changes
    """
    # Validation request
    if validationToken:
        logger.info(f"Webhook validation request received")
        # Must respond with the token in plain text within 5 seconds
        return validationToken
    
    # Notification request
    try:
        body = await request.json()
        logger.info(f"Webhook notification received: {body}")
        
        notifications = body.get("value", [])
        
        for notification in notifications:
            # Validate client state
            # (In production, verify this matches our stored state)
            
            # Process notification in background
            background_tasks.add_task(
                process_notification,
                notification=notification,
                metadata_store=request.app.state.metadata_store,
                vector_store=request.app.state.vector_store
            )
        
        # Must respond with 202 Accepted
        return {"status": "accepted", "count": len(notifications)}
        
    except Exception as e:
        logger.error(f"Error processing notification: {e}")
        # Still return 202 to avoid retries
        return {"status": "error", "message": str(e)}


@router.get("/subscriptions")
async def list_subscriptions(req: Request, connection_id: Optional[str] = None, current_user: User = Depends(require_auth)):
    """List active webhook subscriptions"""
    metadata_store = req.app.state.metadata_store
    
    # Get from database
    async with metadata_store._pool.acquire() as conn:
        if connection_id:
            rows = await conn.fetch("""
                SELECT * FROM webhook_subscriptions 
                WHERE connection_id = $1 AND expiration > NOW()
                ORDER BY created_at DESC
            """, connection_id)
        else:
            rows = await conn.fetch("""
                SELECT * FROM webhook_subscriptions 
                WHERE expiration > NOW()
                ORDER BY created_at DESC
            """)
    
    return [dict(row) for row in rows]


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, req: Request, current_user: User = Depends(require_auth)):
    """Delete a webhook subscription"""
    metadata_store = req.app.state.metadata_store
    
    # Get subscription
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM webhook_subscriptions WHERE id = $1",
            subscription_id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Get connection
    connection = await metadata_store.get_connection(str(row["connection_id"]))
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Delete from Graph API
    client = SharePointClient(
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        client_secret=connection["client_secret_encrypted"]
    )
    
    try:
        await client.authenticate()
        await delete_graph_subscription(client, subscription_id)
        await client.close()
    except Exception as e:
        logger.warning(f"Failed to delete from Graph: {e}")
    
    # Delete from database
    async with metadata_store._pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM webhook_subscriptions WHERE id = $1",
            subscription_id
        )
    
    return {"status": "deleted", "subscription_id": subscription_id}


@router.post("/subscriptions/{subscription_id}/renew")
async def renew_subscription(subscription_id: str, req: Request, current_user: User = Depends(require_auth)):
    """Renew a webhook subscription before it expires"""
    metadata_store = req.app.state.metadata_store
    
    # Get subscription
    async with metadata_store._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM webhook_subscriptions WHERE id = $1",
            subscription_id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Get connection
    connection = await metadata_store.get_connection(str(row["connection_id"]))
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Renew via Graph API
    client = SharePointClient(
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        client_secret=connection["client_secret_encrypted"]
    )
    
    try:
        await client.authenticate()
        new_expiration = datetime.utcnow() + timedelta(days=176)  # Max for drive items
        
        result = await renew_graph_subscription(
            client, 
            subscription_id, 
            new_expiration
        )
        
        # Update database
        async with metadata_store._pool.acquire() as conn:
            await conn.execute("""
                UPDATE webhook_subscriptions 
                SET expiration = $2, updated_at = NOW()
                WHERE id = $1
            """, subscription_id, new_expiration)
        
        await client.close()
        
        return {
            "status": "renewed",
            "subscription_id": subscription_id,
            "new_expiration": new_expiration.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to renew subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Helper Functions
# =============================================================================

async def create_graph_subscription(
    client: SharePointClient,
    resource: str,
    notification_url: str,
    client_state: str,
    expiration_hours: int = 4230
) -> Dict:
    """Create a subscription via Microsoft Graph API"""
    import httpx
    
    expiration = datetime.utcnow() + timedelta(hours=expiration_hours)
    
    payload = {
        "changeType": "created,updated,deleted",
        "notificationUrl": notification_url,
        "resource": resource,
        "expirationDateTime": expiration.isoformat() + "Z",
        "clientState": client_state
    }
    
    response = await client._client.post(
        f"{client.GRAPH_BASE_URL}/subscriptions",
        json=payload
    )
    response.raise_for_status()
    
    return response.json()


async def delete_graph_subscription(client: SharePointClient, subscription_id: str):
    """Delete a subscription via Microsoft Graph API"""
    response = await client._client.delete(
        f"{client.GRAPH_BASE_URL}/subscriptions/{subscription_id}"
    )
    response.raise_for_status()


async def renew_graph_subscription(
    client: SharePointClient,
    subscription_id: str,
    new_expiration: datetime
) -> Dict:
    """Renew a subscription via Microsoft Graph API"""
    payload = {
        "expirationDateTime": new_expiration.isoformat() + "Z"
    }
    
    response = await client._client.patch(
        f"{client.GRAPH_BASE_URL}/subscriptions/{subscription_id}",
        json=payload
    )
    response.raise_for_status()
    
    return response.json()


async def store_subscription(
    metadata_store,
    subscription_id: str,
    connection_id: str,
    resource: str,
    expiration: str,
    client_state: str
):
    """Store subscription in database"""
    async with metadata_store._pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO webhook_subscriptions 
                (id, connection_id, resource, expiration, client_state)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO UPDATE SET
                expiration = EXCLUDED.expiration,
                updated_at = NOW()
        """, subscription_id, connection_id, resource, 
            datetime.fromisoformat(expiration.replace("Z", "+00:00")),
            client_state)


async def process_notification(
    notification: Dict,
    metadata_store,
    vector_store
):
    """
    Process a webhook notification and sync the changed file.
    
    This runs in the background after we've responded to the webhook.
    """
    logger.info(f"Processing notification: {notification}")
    
    try:
        subscription_id = notification.get("subscriptionId")
        change_type = notification.get("changeType")
        resource = notification.get("resource")
        
        # Get subscription from database
        async with metadata_store._pool.acquire() as conn:
            sub_row = await conn.fetchrow(
                "SELECT * FROM webhook_subscriptions WHERE id = $1",
                subscription_id
            )
        
        if not sub_row:
            logger.warning(f"Unknown subscription: {subscription_id}")
            return
        
        connection_id = str(sub_row["connection_id"])
        
        # Get connection
        connection = await metadata_store.get_connection(connection_id)
        if not connection:
            logger.error(f"Connection not found: {connection_id}")
            return
        
        # Create client
        client = SharePointClient(
            tenant_id=connection["tenant_id"],
            client_id=connection["client_id"],
            client_secret=connection["client_secret_encrypted"]
        )
        
        await client.authenticate()
        
        # Get the changed item details
        # The resource path tells us what changed
        # e.g., /drives/{drive-id}/items/{item-id}
        
        if change_type == "deleted":
            # Find and delete the document
            await handle_file_deleted(
                resource=resource,
                connection_id=connection_id,
                metadata_store=metadata_store,
                vector_store=vector_store
            )
        else:
            # Created or Updated - fetch and reindex
            await handle_file_changed(
                client=client,
                resource=resource,
                connection_id=connection_id,
                metadata_store=metadata_store,
                vector_store=vector_store
            )
        
        await client.close()
        
        logger.info(f"Successfully processed {change_type} for {resource}")
        
    except Exception as e:
        logger.error(f"Error processing notification: {e}")


async def handle_file_deleted(
    resource: str,
    connection_id: str,
    metadata_store,
    vector_store
):
    """Handle file deletion - remove from index"""
    # Extract item ID from resource path
    # e.g., /drives/xxx/items/yyy -> yyy
    parts = resource.split("/")
    if "items" in parts:
        item_id = parts[parts.index("items") + 1]
    else:
        logger.warning(f"Could not extract item ID from: {resource}")
        return
    
    # Find document by SharePoint ID
    async with metadata_store._pool.acquire() as conn:
        doc = await conn.fetchrow("""
            SELECT id FROM documents 
            WHERE connection_id = $1 AND sharepoint_id = $2
        """, connection_id, item_id)
    
    if doc:
        document_id = str(doc["id"])
        
        # Delete from vector store
        await vector_store.delete_by_document(document_id)
        
        # Delete from metadata
        await metadata_store.delete_chunks_by_document(document_id)
        
        async with metadata_store._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM documents WHERE id = $1",
                document_id
            )
        
        logger.info(f"Deleted document: {document_id}")


async def handle_file_changed(
    client: SharePointClient,
    resource: str,
    connection_id: str,
    metadata_store,
    vector_store
):
    """Handle file creation/update - fetch and reindex"""
    from app.processing.extractor import DocumentExtractor
    from app.processing.chunker import TextChunker
    from app.processing.embedder import TextEmbedder
    
    # Get file info from Graph API
    response = await client._client.get(
        f"{client.GRAPH_BASE_URL}{resource}"
    )
    
    if response.status_code != 200:
        logger.error(f"Failed to get item: {response.text}")
        return
    
    item = response.json()
    
    # Skip folders
    if "folder" in item:
        logger.info(f"Skipping folder: {item.get('name')}")
        return
    
    # Check file type
    name = item.get("name", "")
    ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    
    if ext not in client.SUPPORTED_EXTENSIONS:
        logger.info(f"Skipping unsupported file type: {name}")
        return
    
    logger.info(f"Processing changed file: {name}")
    
    # Download content
    download_url = item.get("@microsoft.graph.downloadUrl")
    if not download_url:
        # Get download URL
        response = await client._client.get(
            f"{client.GRAPH_BASE_URL}{resource}/content",
            follow_redirects=False
        )
        if response.status_code == 302:
            download_url = response.headers.get("Location")
    
    if not download_url:
        logger.error(f"Could not get download URL for: {name}")
        return
    
    import httpx
    async with httpx.AsyncClient() as http:
        response = await http.get(download_url)
        content = response.content
    
    # Process file (same as import pipeline)
    extractor = DocumentExtractor()
    chunker = TextChunker()
    embedder = TextEmbedder()
    
    # Extract text
    extraction = await extractor.extract(
        content=content,
        mime_type=item.get("file", {}).get("mimeType", ""),
        filename=name
    )
    
    if not extraction.text.strip():
        logger.warning(f"No text extracted from: {name}")
        return
    
    # Create/update document record
    doc = await metadata_store.upsert_document(
        connection_id=connection_id,
        sharepoint_id=item["id"],
        name=name,
        path=item.get("parentReference", {}).get("path", "") + "/" + name,
        mime_type=item.get("file", {}).get("mimeType", ""),
        size_bytes=item.get("size", 0),
        web_url=item.get("webUrl"),
        content_hash=item.get("file", {}).get("hashes", {}).get("sha256Hash")
    )
    document_id = str(doc["id"])
    
    # Chunk text
    chunks = chunker.chunk_text(extraction.text)
    
    if not chunks:
        return
    
    # Generate embeddings
    embeddings = await embedder.embed_batch([c.content for c in chunks])
    
    # Delete old vectors/chunks
    await vector_store.delete_by_document(document_id)
    await metadata_store.delete_chunks_by_document(document_id)
    
    # Store new vectors
    vectors = []
    chunk_records = []
    
    for chunk, embedding in zip(chunks, embeddings):
        vector_id = f"{document_id}_{chunk.index}"
        
        vectors.append({
            "id": vector_id,
            "embedding": embedding,
            "content": chunk.content,
            "document_id": document_id,
            "document_name": name,
            "chunk_index": chunk.index,
            "connection_id": connection_id,
            "page_number": chunk.page_number,
            "web_url": item.get("webUrl")
        })
        
        chunk_records.append({
            "index": chunk.index,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "page_number": chunk.page_number,
            "vector_id": vector_id
        })
    
    await vector_store.upsert_vectors(vectors)
    await metadata_store.create_chunks(document_id, chunk_records)
    
    # Update document status
    await metadata_store.update_document_status(
        document_id=document_id,
        status="indexed",
        chunk_count=len(chunks)
    )
    
    logger.info(f"Indexed {name}: {len(chunks)} chunks")
