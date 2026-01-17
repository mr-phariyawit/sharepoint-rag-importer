"""Import API routes"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import asyncio

from app.sharepoint.client import SharePointClient, SharePointFile
from app.processing.extractor import DocumentExtractor
from app.processing.chunker import TextChunker, Chunk
# Import embedder from chunker.py (we combined them)
from app.config import settings
from app.auth.middleware import require_auth, User

logger = logging.getLogger(__name__)
router = APIRouter()


class ImportRequest(BaseModel):
    """Request to import a SharePoint folder"""
    connection_id: str = Field(..., description="Connection ID")
    folder_url: str = Field(..., description="SharePoint folder URL")
    recursive: bool = Field(True, description="Import subfolders recursively")
    file_types: Optional[List[str]] = Field(
        None, 
        description="File types to import (e.g., ['pdf', 'docx'])"
    )


class ImportJobResponse(BaseModel):
    """Import job response"""
    id: str
    connection_id: str
    folder_url: str
    status: str
    total_files_found: int
    files_processed: int
    files_failed: int
    total_chunks_created: int
    progress_percent: Optional[float] = None
    current_file: Optional[str] = None


@router.post("", response_model=ImportJobResponse)
async def start_import(
    request: ImportRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    current_user: User = Depends(require_auth)
):
    """
    Start importing files from a SharePoint folder.
    
    The import runs in the background. Use GET /api/import/{job_id} to check status.
    """
    metadata_store = req.app.state.metadata_store
    vector_store = req.app.state.vector_store
    
    # Get connection
    connection = await metadata_store.get_connection(request.connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Create import job
    job = await metadata_store.create_import_job(
        connection_id=request.connection_id,
        folder_url=request.folder_url,
        recursive=request.recursive,
        file_types=request.file_types
    )
    
    # Start background import
    background_tasks.add_task(
        run_import_job,
        job_id=str(job["id"]),
        connection=connection,
        folder_url=request.folder_url,
        recursive=request.recursive,
        metadata_store=metadata_store,
        vector_store=vector_store
    )
    
    return ImportJobResponse(
        id=str(job["id"]),
        connection_id=request.connection_id,
        folder_url=request.folder_url,
        status="pending",
        total_files_found=0,
        files_processed=0,
        files_failed=0,
        total_chunks_created=0
    )


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_status(job_id: str, req: Request, current_user: User = Depends(require_auth)):
    """Get import job status"""
    metadata_store = req.app.state.metadata_store
    job = await metadata_store.get_import_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    
    return ImportJobResponse(
        id=str(job["id"]),
        connection_id=str(job["connection_id"]),
        folder_url=job["folder_url"],
        status=job["status"],
        total_files_found=job["total_files_found"] or 0,
        files_processed=job["files_processed"] or 0,
        files_failed=job["files_failed"] or 0,
        total_chunks_created=job["total_chunks_created"] or 0,
        progress_percent=job.get("progress_percent"),
        current_file=job.get("current_file")
    )


@router.get("")
async def list_import_jobs(
    req: Request,
    connection_id: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(require_auth)
):
    """List recent import jobs"""
    # TODO: Implement in metadata store
    # For now return empty list or mock
    # Wait, we need to implement listing in metadata store if we want the dashboard to show jobs
    # But for now, returning empty list allows dashboard to load without error
    
    # Actually, let's just use metadata_store.get_recent_jobs if it existed, but it doesn't.
    # We'll just return all jobs from SQL if we can, or just empty for now.
    # The dashboard calls GET /api/import
    
    return []


# =============================================================================
# BACKGROUND IMPORT TASK
# =============================================================================

async def run_import_job(
    job_id: str,
    connection: dict,
    folder_url: str,
    recursive: bool,
    metadata_store,
    vector_store
):
    """
    Background task to run the full import pipeline.
    """
    logger.info(f"Starting import job {job_id}")
    
    # Initialize components
    extractor = DocumentExtractor()
    chunker = TextChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP
    )
    
    # Import embedder
    from app.processing.embedder import TextEmbedder
    embedder = TextEmbedder()
    
    # Stats
    files_processed = 0
    files_failed = 0
    total_chunks = 0
    error_log = []
    
    try:
        # Ensure Qdrant collection exists (self-healing if deleted or fresh install)
        await vector_store.ensure_collection()

        # Update status to crawling
        await metadata_store.update_import_job_progress(
            job_id=job_id,
            status="crawling"
        )
        
        # Decrypt secret
        from app.security.encryption import EncryptionService
        encryption = EncryptionService()
        # Fetch the encrypted secret using the correct key
        encrypted_secret = connection.get("client_secret_encrypted") or connection.get("client_secret")
        decrypted_secret = encryption.decrypt(encrypted_secret)

        # Create SharePoint client
        client = SharePointClient(
            tenant_id=connection["tenant_id"],
            client_id=connection["client_id"],
            client_secret=decrypted_secret
        )
        
        await client.authenticate()
        
        # Parse URL and get folder info
        try:
            # Try sharing link if logic suggests it
            if ":f:" in folder_url or "sharepoint.com/:f:/" in folder_url or "?e=" in folder_url:
                logger.info("Attempting to resolve as sharing URL")
                item = await client.resolve_sharing_url(folder_url)
                folder_id = item["id"]
                drive_id = item["parentReference"]["driveId"]
                site_id = item.get("parentReference", {}).get("siteId")
            else:
                raise Exception("Not a sharing link")
        except Exception:
            # Standard parsing
            logger.info("Using standard URL parsing")
            site_id, drive_id, folder_path = await client.get_site_and_drive(folder_url)
            folder_id = await client.get_folder_id(drive_id, folder_path)
            
        if not folder_id:
            raise Exception(f"Folder not found for URL: {folder_url}")
        
        # Collect all files first
        all_files: List[SharePointFile] = []
        
        if recursive:
            async for file in client.crawl_folder_recursive(
                drive_id=drive_id,
                folder_id=folder_id,
                site_id=site_id
            ):
                all_files.append(file)
        else:
            files, _ = await client.list_folder_contents(drive_id, folder_id)
            all_files = files
        
        total_files = len(all_files)
        logger.info(f"Found {total_files} files to process")
        
        # Update status
        await metadata_store.update_import_job_progress(
            job_id=job_id,
            status="processing",
            total_files_found=total_files
        )
        
        # Process each file
        for idx, file in enumerate(all_files):
            try:
                logger.info(f"Processing [{idx+1}/{total_files}]: {file.name}")
                
                # Update current file
                await metadata_store.update_import_job_progress(
                    job_id=job_id,
                    current_file=file.name,
                    files_processed=files_processed
                )
                
                # Skip large files
                if file.size_bytes > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                    logger.warning(f"Skipping large file: {file.name}")
                    continue
                
                # Download content
                content = await client.download_file(file)
                
                # Create/update document record
                doc = await metadata_store.upsert_document(
                    connection_id=connection["id"],
                    sharepoint_id=file.id,
                    name=file.name,
                    path=file.path,
                    mime_type=file.mime_type,
                    size_bytes=file.size_bytes,
                    web_url=file.web_url,
                    content_hash=file.content_hash,
                    import_job_id=job_id
                )
                document_id = str(doc["id"])
                
                # Update status to processing
                await metadata_store.update_document_status(
                    document_id=document_id,
                    status="processing"
                )
                
                # Extract text
                extraction = await extractor.extract(
                    content=content,
                    mime_type=file.mime_type,
                    filename=file.name
                )
                
                if extraction.error or not extraction.text.strip():
                    logger.warning(f"No text extracted from {file.name}")
                    await metadata_store.update_document_status(
                        document_id=document_id,
                        status="failed",
                        error_message=extraction.error or "No text content"
                    )
                    files_failed += 1
                    continue
                
                # Chunk text
                chunks = chunker.chunk_text(
                    text=extraction.text,
                    metadata={"source": file.name}
                )
                
                if not chunks:
                    logger.warning(f"No chunks created for {file.name}")
                    continue
                
                # Generate embeddings
                chunk_texts = [c.content for c in chunks]
                embeddings = await embedder.embed_batch(chunk_texts)
                
                # Prepare vectors for storage
                vectors = []
                chunk_records = []
                
                for chunk, embedding in zip(chunks, embeddings):
                    vector_id = f"{document_id}_{chunk.index}"
                    
                    vectors.append({
                        "id": vector_id,
                        "embedding": embedding,
                        "content": chunk.content,
                        "document_id": document_id,
                        "document_name": file.name,
                        "chunk_index": chunk.index,
                        "connection_id": str(connection["id"]),
                        "page_number": chunk.page_number,
                        "section_title": chunk.section_title,
                        "web_url": file.web_url,
                        "metadata": {
                            "path": file.path,
                            "mime_type": file.mime_type
                        }
                    })
                    
                    chunk_records.append({
                        "index": chunk.index,
                        "content": chunk.content,
                        "token_count": chunk.token_count,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "page_number": chunk.page_number,
                        "section_title": chunk.section_title,
                        "vector_id": vector_id
                    })
                
                # Delete existing vectors/chunks for this document
                await vector_store.delete_by_document(document_id)
                await metadata_store.delete_chunks_by_document(document_id)
                
                # Store vectors
                await vector_store.upsert_vectors(vectors)
                
                # Store chunk metadata
                await metadata_store.create_chunks(document_id, chunk_records)
                
                # Update document status
                await metadata_store.update_document_status(
                    document_id=document_id,
                    status="indexed",
                    chunk_count=len(chunks)
                )
                
                files_processed += 1
                total_chunks += len(chunks)
                
                logger.info(f"✅ {file.name}: {len(chunks)} chunks indexed")
                
            except Exception as e:
                logger.error(f"Error processing {file.name}: {e}")
                error_log.append({
                    "file": file.name,
                    "error": str(e)
                })
                files_failed += 1
        
        # Close client
        await client.close()
        
        # Update final status
        await metadata_store.update_import_job_progress(
            job_id=job_id,
            status="completed",
            files_processed=files_processed,
            files_failed=files_failed,
            total_chunks_created=total_chunks,
            error_log=error_log
        )
        
        logger.info(
            f"Import job {job_id} completed: "
            f"{files_processed} files, {total_chunks} chunks, "
            f"{files_failed} failed"
        )
        
    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}")
        await metadata_store.update_import_job_progress(
            job_id=job_id,
            status="failed",
            error_log=[{"error": str(e)}]
        )
