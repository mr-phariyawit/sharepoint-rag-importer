"""Connection management API routes"""

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from app.sharepoint.client import SharePointClient, extract_tenant_from_url
from app.security.encryption import EncryptionService
from app.auth.middleware import require_auth, User

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateConnectionRequest(BaseModel):
    """Request to create a new SharePoint connection"""
    name: str = Field(..., description="Connection name")
    folder_url: str = Field(..., description="SharePoint folder URL (sharing link or direct URL)")
    client_id: str = Field(..., description="App Registration Client ID")
    client_secret: str = Field(..., description="App Registration Client Secret")
    tenant_id: Optional[str] = Field(None, description="Azure AD Tenant ID (optional - auto-extracted from URL if not provided)")


class ConnectionResponse(BaseModel):
    """Connection response model"""
    id: str
    name: str
    tenant_id: str
    client_id: str
    status: str
    default_folder_url: Optional[str] = None
    total_documents: Optional[int] = 0
    indexed_documents: Optional[int] = 0
    total_chunks: Optional[int] = 0
    created_at: str


@router.post("", response_model=ConnectionResponse)
async def create_connection(
    request: CreateConnectionRequest,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """
    Create a new SharePoint connection.

    Provide the SharePoint folder URL and Azure AD app credentials.
    The tenant is automatically extracted from the SharePoint URL.

    Requires Azure AD App Registration with the following permissions:
    - Files.Read.All
    - Sites.Read.All
    """
    metadata_store = req.app.state.metadata_store

    # Use provided tenant_id or extract from SharePoint URL
    if request.tenant_id:
        tenant_id = request.tenant_id
        logger.info(f"Using provided tenant: {tenant_id}")
    else:
        try:
            tenant_id = extract_tenant_from_url(request.folder_url)
            logger.info(f"Extracted tenant: {tenant_id} from URL: {request.folder_url}")
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e)
            )

    # Test connection with tenant
    client = SharePointClient(
        tenant_id=tenant_id,
        client_id=request.client_id,
        client_secret=request.client_secret
    )

    try:
        await client.authenticate()
        validation = await client.validate_connection()

        # Get actual tenant GUID if available from validation
        actual_tenant_id = validation.get("tenant_id", tenant_id)

        await client.close()

        if not validation.get("valid"):
            raise HTTPException(
                status_code=400,
                detail="Failed to validate SharePoint connection. Check your credentials."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Connection failed: {str(e)}"
        )

    # Encrypt client secret
    encryption = EncryptionService()
    encrypted_secret = encryption.encrypt(request.client_secret)

    # Create connection record with folder URL
    connection = await metadata_store.create_connection(
        name=request.name,
        tenant_id=actual_tenant_id,
        client_id=request.client_id,
        client_secret=encrypted_secret,
        default_folder_url=request.folder_url
    )

    # Update status to connected
    await metadata_store.update_connection_status(
        connection_id=str(connection["id"]),
        status="connected"
    )

    return ConnectionResponse(
        id=str(connection["id"]),
        name=connection["name"],
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        status="connected",
        default_folder_url=request.folder_url,
        created_at=str(connection["created_at"])
    )


@router.get("", response_model=List[ConnectionResponse])
async def list_connections(req: Request, current_user: User = Depends(require_auth)):
    """List all SharePoint connections"""
    metadata_store = req.app.state.metadata_store
    connections = await metadata_store.list_connections()

    return [
        ConnectionResponse(
            id=str(c["id"]),
            name=c["name"],
            tenant_id=c["tenant_id"],
            client_id=c["client_id"],
            status=c["status"],
            default_folder_url=c.get("default_folder_url"),
            total_documents=c.get("total_documents", 0),
            indexed_documents=c.get("indexed_documents", 0),
            total_chunks=c.get("total_chunks", 0),
            created_at=str(c["created_at"])
        )
        for c in connections
    ]


@router.get("/{connection_id}")
async def get_connection(connection_id: str, req: Request, current_user: User = Depends(require_auth)):
    """Get connection details"""
    metadata_store = req.app.state.metadata_store
    connection = await metadata_store.get_connection(connection_id)
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    return connection


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str, req: Request, current_user: User = Depends(require_auth)):
    """Delete a connection and all its data"""
    metadata_store = req.app.state.metadata_store
    vector_store = req.app.state.vector_store
    
    # Delete vectors
    await vector_store.delete_by_connection(connection_id)
    
    # Delete connection and all related data (cascade)
    await metadata_store.delete_connection(connection_id)
    
    return {"status": "deleted", "connection_id": connection_id}


@router.get("/{connection_id}/drives")
async def list_connection_drives(connection_id: str, req: Request, current_user: User = Depends(require_auth)):
    """List document libraries (drives) for a connection"""
    metadata_store = req.app.state.metadata_store
    
    # Get connection
    connection = await metadata_store.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Decrypt secret
    encryption = EncryptionService()
    try:
        encrypted_secret = connection.get("client_secret_encrypted")
        if not encrypted_secret:
             # Legacy fallback or error
             client_secret = connection.get("client_secret")
             if not client_secret:
                 raise ValueError("No client secret found")
        else:
             try:
                 client_secret = encryption.decrypt(encrypted_secret)
             except Exception:
                 client_secret = encrypted_secret
    except Exception as e:
        logger.error(f"Failed to decrypt secret: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve connection credentials")
    
    # Init client
    client = SharePointClient(
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        client_secret=client_secret
    )
    
    try:
        await client.authenticate()
        drives = await client.list_drives()
        await client.close()
        return drives
    except Exception as e:
        await client.close()
        logger.error(f"Failed to list drives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{connection_id}/browse")
async def browse_connection_files(
    connection_id: str,
    req: Request,
    drive_id: str = Query(..., description="Drive ID to browse"),
    folder_id: str = Query("root", description="Folder ID to list (default: root)"),
    current_user: User = Depends(require_auth)
):
    """List files and folders in a SharePoint location"""
    metadata_store = req.app.state.metadata_store
    
    # Get connection
    connection = await metadata_store.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Decrypt secret
    encryption = EncryptionService()
    try:
        encrypted_secret = connection.get("client_secret_encrypted")
        if not encrypted_secret:
             client_secret = connection.get("client_secret")
             if not client_secret:
                 raise ValueError("No client secret found")
        else:
             try:
                 client_secret = encryption.decrypt(encrypted_secret)
             except Exception:
                 client_secret = encrypted_secret
    except Exception as e:
        logger.error(f"Failed to decrypt secret: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve connection credentials")
    
    # Init client
    client = SharePointClient(
        tenant_id=connection["tenant_id"],
        client_id=connection["client_id"],
        client_secret=client_secret
    )
    
    try:
        await client.authenticate()
        files, folders = await client.list_folder_contents(
            drive_id=drive_id,
            folder_id=folder_id
        )
        await client.close()
        
        return {
            "folders": [
                {
                    "id": f.id,
                    "name": f.name,
                    "path": f.path,
                    "child_count": f.child_count,
                    "web_url": f.web_url
                }
                for f in folders
            ],
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "size": f.size_bytes,
                    "web_url": f.web_url,
                    "created_at": f.created_at,
                    "modified_at": f.modified_at
                }
                for f in files
            ]
        }
    except Exception as e:
        await client.close()
        logger.error(f"Failed to browse folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))
