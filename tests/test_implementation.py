
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, BackgroundTasks
from app.api.connections import create_connection, delete_connection
from app.api.import_routes import start_import, list_import_jobs
from app.api.connections import ConnectionRequest
from app.api.import_routes import ImportRequest

@pytest.mark.asyncio
async def test_create_connection_encrypts_secret():
    # Mock request and metadata store
    mock_metadata = AsyncMock()
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.metadata_store = mock_metadata
    
    # Mock EncryptionService
    with patch("app.security.encryption.EncryptionService") as MockEncryption:
        mock_service = MockEncryption.return_value
        mock_service.encrypt.return_value = "encrypted_secret"
        
        # Call API
        payload = ConnectionRequest(
            name="Test Connection",
            tenant_id="tenant-123",
            client_id="client-456",
            client_secret="plain_secret"
        )
        
        # Mock create_connection return
        mock_metadata.create_connection.return_value = {"id": "conn-123"}
        
        await create_connection(payload, mock_request)
        
        # Verify encryption was called
        mock_service.encrypt.assert_called_with("plain_secret")
        
        # Verify metadata store called with encrypted secret
        mock_metadata.create_connection.assert_called_once()
        call_args = mock_metadata.create_connection.call_args[1]
        assert call_args["client_secret"] == "encrypted_secret"

@pytest.mark.asyncio
async def test_delete_connection_cascades():
    # Mock request and stores
    mock_metadata = AsyncMock()
    mock_vector = AsyncMock()
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.metadata_store = mock_metadata
    mock_request.app.state.vector_store = mock_vector
    
    # Call API
    await delete_connection("conn-123", mock_request)
    
    # Verify metadata store delete connection called
    mock_metadata.delete_connection.assert_called_with("conn-123")
    # Verify vector store delete called
    mock_vector.delete_by_connection.assert_called_with("conn-123")

@pytest.mark.asyncio
async def test_list_import_jobs_calls_store():
    # Mock request and metadata store
    mock_metadata = AsyncMock()
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.metadata_store = mock_metadata
    
    # Mock return value
    mock_metadata.list_import_jobs.return_value = [
        {
            "id": "job-1",
            "connection_id": "conn-1",
            "status": "completed",
            "created_at": "2024-01-01"
        }
    ]
    
    # Call API
    results = await list_import_jobs(mock_request, connection_id="conn-1", limit=10)
    
    # Verify metadata store called
    mock_metadata.list_import_jobs.assert_called_with(
        connection_id="conn-1",
        status=None,
        limit=10
    )
    
    # Verify result formatting
    assert len(results) == 1
    assert results[0].id == "job-1"

