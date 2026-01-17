# app/storage/vector_store.py
"""Qdrant vector database operations"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range,
    SearchParams, QuantizationSearchParams
)
import uuid
import logging

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Search result from vector store"""
    id: str
    score: float
    content: str
    document_id: str
    document_name: str
    chunk_index: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    web_url: Optional[str] = None
    metadata: Dict[str, Any] = None


class VectorStore:
    """
    Qdrant vector store for document embeddings.
    """
    
    def __init__(
        self,
        url: str = None,
        collection_name: str = None
    ):
        self.url = url or settings.QDRANT_URL
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self._client: Optional[AsyncQdrantClient] = None
    
    async def connect(self):
        """Connect to Qdrant"""
        self._client = AsyncQdrantClient(url=self.url)
        logger.info(f"Connected to Qdrant at {self.url}")
    
    async def health_check(self) -> bool:
        """Check if Qdrant is healthy"""
        try:
            await self._client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
    
    async def ensure_collection(self):
        """Create collection if it doesn't exist"""
        collections = await self._client.get_collections()
        collection_names = [c.name for c in collections.collections]
        
        if self.collection_name not in collection_names:
            await self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimensions,
                    distance=Distance.COSINE
                ),
                # Enable payload indexing for filtering
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=10000
                )
            )
            
            # Create payload indexes for efficient filtering
            await self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="connection_id",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            await self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            # Additional indexes for Phase 3 filtering
            await self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_name",
                field_schema=models.PayloadSchemaType.TEXT
            )
            await self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.mime_type",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            # Note: DATETIME schema requires newer client/server compatibility
            # Skipping indexed_at index for now to ensure stability with current library versions
            
            logger.info(f"Created collection: {self.collection_name}")
        else:
            logger.info(f"Collection exists: {self.collection_name}")
    
    async def upsert_vectors(
        self,
        vectors: List[Dict[str, Any]]
    ) -> int:
        """
        Upsert vectors with metadata.
        
        Args:
            vectors: List of dicts with keys:
                - id: unique ID
                - embedding: vector
                - content: text content
                - document_id: parent document ID
                - document_name: file name
                - chunk_index: chunk position
                - connection_id: source connection
                - page_number: optional page
                - section_title: optional section
                - web_url: optional link to source
                - metadata: additional metadata
        
        Returns:
            Number of vectors upserted
        """
        points = []
        
        for vec in vectors:
            point = PointStruct(
                id=vec.get("id") or str(uuid.uuid4()),
                vector=vec["embedding"],
                payload={
                    "content": vec["content"],
                    "document_id": vec["document_id"],
                    "document_name": vec["document_name"],
                    "chunk_index": vec["chunk_index"],
                    "connection_id": vec.get("connection_id"),
                    "page_number": vec.get("page_number"),
                    "section_title": vec.get("section_title"),
                    "web_url": vec.get("web_url"),
                    "metadata": vec.get("metadata", {})
                }
            )
            points.append(point)
        
        # Upsert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch_points = points[i:i + batch_size]
            
            batch_points = points[i:i + batch_size]
            
            # Manual construction for debugging and bypassing client serialization issues
            batch_ids = []
            batch_vectors = []
            batch_payloads = []
            
            import json
            import httpx
            import uuid
            
            for p in batch_points:
                # ID: Qdrant requires UUID or Int. We have arbitrary string "uuid_index".
                # We must hash it to a valid UUID.
                raw_id = str(p.id)
                pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
                
                # Vector: Ensure list of floats
                vec = p.vector
                if hasattr(vec, "tolist"):
                    vec = vec.tolist()
                
                # Payload: CLEAN and SANITIZE
                raw_payload = p.payload or {}
                valid_payload = {k: v for k, v in raw_payload.items() if v is not None}
                
                try:
                    # Brute force sanitization
                    sanitized = json.loads(json.dumps(valid_payload, default=str))
                except Exception as e:
                    logger.error(f"Payload sanitization failed: {e}")
                    sanitized = {} 
                    
                batch_ids.append(pid)
                batch_vectors.append(vec)
                batch_payloads.append(sanitized)

            try:
                # Direct HTTP request to Qdrant using BATCH format
                qdrant_url = self.url if self.url else "http://qdrant:6333"
                if qdrant_url.endswith("/"):
                    qdrant_url = qdrant_url[:-1]
                    
                body = {
                    "batch": {
                        "ids": batch_ids,
                        "vectors": batch_vectors,
                        "payloads": batch_payloads
                    }
                }
                    
                async with httpx.AsyncClient() as client:
                    resp = await client.put(
                        f"{qdrant_url}/collections/{self.collection_name}/points?wait=true",
                        json=body,
                        timeout=30.0
                    )
                    
                    if resp.status_code != 200:
                        logger.error(f"Manual Batch Upsert Failed: {resp.status_code} - {resp.text}")
                        # Log sample body (truncated)
                        logger.error(f"Sent Body IDs sample: {batch_ids[:3]}")
                        raise Exception(f"Qdrant Error: {resp.text}")
                        
            except Exception as e:
                logger.error(f"Failed to upsert batch {i}. Error: {e}")
                logger.error(f"Batch stats: Points={len(batch_ids)}")
                raise e

        
        logger.info(f"Upserted {len(points)} vectors")
        return len(points)
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        connection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        min_score: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        """
        Search for similar vectors with optional filtering.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results
            connection_id: Filter by connection
            document_ids: Filter by specific documents
            min_score: Minimum similarity score
            filters: Advanced filters dict with keys:
                - file_types: List[str] (e.g., ["pdf", "docx"])
                - folder_path: str (prefix match)
                - date_from: datetime
                - date_to: datetime
        
        Returns:
            List of search results
        """
        # Build filter
        filter_conditions = []
        
        if connection_id:
            filter_conditions.append(
                FieldCondition(
                    key="connection_id",
                    match=MatchValue(value=connection_id)
                )
            )
        
        if document_ids:
            filter_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids)
                )
            )
        
        # Advanced filters
        if filters:
            # Filter by file types (via document_name extension)
            if filters.get("file_types"):
                # Use MatchAny with file extensions in document_name
                # Note: This is a workaround - ideally we'd have a separate mime_type field
                file_type_conditions = []
                for ext in filters["file_types"]:
                    file_type_conditions.append(
                        FieldCondition(
                            key="document_name",
                            match=models.MatchText(text=f".{ext}")
                        )
                    )
                if file_type_conditions:
                    filter_conditions.append(
                        models.Filter(should=file_type_conditions)
                    )
            
            # Filter by folder path prefix
            if filters.get("folder_path"):
                filter_conditions.append(
                    FieldCondition(
                        key="metadata.path",
                        match=models.MatchText(text=filters["folder_path"])
                    )
                )
        
        search_filter = Filter(must=filter_conditions) if filter_conditions else None
        
        # Search
        results = await self._client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=search_filter,
            score_threshold=min_score,
            with_payload=True
        )
        
        # Convert to results
        search_results = []
        for hit in results:
            payload = hit.payload or {}
            search_results.append(VectorSearchResult(
                id=str(hit.id),
                score=hit.score,
                content=payload.get("content", ""),
                document_id=payload.get("document_id", ""),
                document_name=payload.get("document_name", ""),
                chunk_index=payload.get("chunk_index", 0),
                page_number=payload.get("page_number"),
                section_title=payload.get("section_title"),
                web_url=payload.get("web_url"),
                metadata=payload.get("metadata", {})
            ))
        
        return search_results
    
    async def delete_by_document(self, document_id: str) -> int:
        """Delete all vectors for a document"""
        result = await self._client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
        )
        logger.info(f"Deleted vectors for document {document_id}")
        return result.status
    
    async def delete_by_connection(self, connection_id: str) -> int:
        """Delete all vectors for a connection"""
        result = await self._client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="connection_id",
                            match=MatchValue(value=connection_id)
                        )
                    ]
                )
            )
        )
        logger.info(f"Deleted vectors for connection {connection_id}")
        return result.status
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        info = await self._client.get_collection(self.collection_name)
        return {
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "points_count": info.points_count,
            "status": info.status
        }


# =============================================================================
# METADATA STORE
# =============================================================================

# app/storage/metadata_store.py
"""PostgreSQL metadata storage"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncpg
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class MetadataStore:
    """
    PostgreSQL store for document and connection metadata.
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or settings.DATABASE_URL
        # Convert SQLAlchemy URL to asyncpg format
        self.database_url = self.database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        self._pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create connection pool"""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
            statement_cache_size=0
        )
        logger.info("Connected to PostgreSQL")
    
    async def disconnect(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTIONS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def create_connection(
        self,
        name: str,
        tenant_id: str,
        client_id: str,
        client_secret: str
    ) -> Dict[str, Any]:
        """Create a new SharePoint connection"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO connections (name, tenant_id, client_id, client_secret_encrypted)
                VALUES ($1, $2, $3, $4)
                RETURNING id, name, tenant_id, client_id, status, created_at
            """, name, tenant_id, client_id, client_secret)  # TODO: encrypt
            
            return dict(row)
    
    async def get_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get connection by ID"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, name, tenant_id, client_id, client_secret_encrypted,
                       status, last_error, created_at, updated_at
                FROM connections WHERE id = $1
            """, connection_id)
            
            return dict(row) if row else None
    
    async def list_connections(self) -> List[Dict[str, Any]]:
        """List all connections"""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.*, cs.total_documents, cs.indexed_documents, 
                       cs.total_chunks, cs.total_size_bytes
                FROM connections c
                LEFT JOIN connection_stats cs ON c.id = cs.connection_id
                ORDER BY c.created_at DESC
            """)
            return [dict(row) for row in rows]
    
    async def update_connection_status(
        self,
        connection_id: str,
        status: str,
        error: str = None
    ):
        """Update connection status"""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE connections 
                SET status = $2, last_error = $3, updated_at = NOW()
                WHERE id = $1
            """, connection_id, status, error)

    async def delete_connection(self, connection_id: str):
        """Delete a connection and all related data (cascade)"""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # 1. Delete chunks (via documents)
                await conn.execute("""
                    DELETE FROM chunks 
                    WHERE document_id IN (
                        SELECT id FROM documents WHERE connection_id = $1
                    )
                """, connection_id)
                
                # 2. Delete documents
                await conn.execute(
                    "DELETE FROM documents WHERE connection_id = $1", 
                    connection_id
                )
                
                # 3. Delete import jobs
                await conn.execute(
                    "DELETE FROM import_jobs WHERE connection_id = $1", 
                    connection_id
                )
                
                # 4. Delete connection
                await conn.execute(
                    "DELETE FROM connections WHERE id = $1", 
                    connection_id
                )
    
    # ─────────────────────────────────────────────────────────────────────────
    # IMPORT JOBS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def create_import_job(
        self,
        connection_id: str,
        folder_url: str,
        folder_name: str = None,
        recursive: bool = True,
        file_types: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new import job"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO import_jobs 
                    (connection_id, folder_url, folder_name, recursive, file_types)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, connection_id, folder_url, status, created_at
            """, connection_id, folder_url, folder_name, recursive, file_types)
            
            return dict(row)
    
    async def get_import_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get import job by ID"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM import_jobs WHERE id = $1
            """, job_id)
            return dict(row) if row else None
            
    async def list_import_jobs(
        self,
        connection_id: str = None,
        status: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List import jobs with filtering"""
        conditions = []
        values = []
        param_idx = 1
        
        if connection_id:
            conditions.append(f"connection_id = ${param_idx}")
            values.append(connection_id)
            param_idx += 1
            
        if status:
            conditions.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1
            
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        values.append(limit)
        
        query = f"""
            SELECT * FROM import_job_summary 
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
            return [dict(row) for row in rows]
    
    async def update_import_job_progress(
        self,
        job_id: str,
        status: str = None,
        total_files_found: int = None,
        files_processed: int = None,
        files_failed: int = None,
        current_file: str = None,
        total_chunks_created: int = None,
        error_log: List[Dict] = None
    ):
        """Update import job progress"""
        updates = []
        values = [job_id]
        param_idx = 2
        
        if status:
            updates.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1
            
            if status == "crawling":
                updates.append("started_at = NOW()")
            elif status in ("completed", "failed"):
                updates.append("completed_at = NOW()")
        
        if total_files_found is not None:
            updates.append(f"total_files_found = ${param_idx}")
            values.append(total_files_found)
            param_idx += 1
        
        if files_processed is not None:
            updates.append(f"files_processed = ${param_idx}")
            values.append(files_processed)
            param_idx += 1
        
        if files_failed is not None:
            updates.append(f"files_failed = ${param_idx}")
            values.append(files_failed)
            param_idx += 1
        
        if current_file is not None:
            updates.append(f"current_file = ${param_idx}")
            values.append(current_file)
            param_idx += 1
        
        if total_chunks_created is not None:
            updates.append(f"total_chunks_created = ${param_idx}")
            values.append(total_chunks_created)
            param_idx += 1
        
        if error_log is not None:
            updates.append(f"error_log = ${param_idx}")
            values.append(json.dumps(error_log))
            param_idx += 1
        
        if updates:
            query = f"UPDATE import_jobs SET {', '.join(updates)} WHERE id = $1"
            async with self._pool.acquire() as conn:
                await conn.execute(query, *values)
    
    # ─────────────────────────────────────────────────────────────────────────
    # DOCUMENTS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def upsert_document(
        self,
        connection_id: str,
        sharepoint_id: str,
        name: str,
        path: str,
        mime_type: str,
        size_bytes: int,
        web_url: str = None,
        content_hash: str = None,
        import_job_id: str = None
    ) -> Dict[str, Any]:
        """Upsert document record"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO documents 
                    (connection_id, sharepoint_id, name, path, mime_type, 
                     size_bytes, web_url, content_hash, import_job_id, updated_at)
                VALUES ($1::uuid, $2::text, $3::text, $4::text, $5::text, $6::bigint, $7::text, $8::text, $9::uuid, NOW())
                ON CONFLICT (connection_id, sharepoint_id) 
                DO UPDATE SET
                    name = EXCLUDED.name,
                    path = EXCLUDED.path,
                    mime_type = EXCLUDED.mime_type,
                    size_bytes = EXCLUDED.size_bytes,
                    web_url = EXCLUDED.web_url,
                    content_hash = EXCLUDED.content_hash,
                    import_job_id = EXCLUDED.import_job_id,
                    updated_at = NOW(),
                    status = 'pending', -- Reset status to pending on update
                    error_message = NULL
                RETURNING *
            """, connection_id, sharepoint_id, name, path, mime_type,
                size_bytes, web_url, content_hash, import_job_id)
            
            return dict(row)
    
    async def update_document_status(
        self,
        document_id: str,
        status: str,
        chunk_count: int = None,
        error_message: str = None
    ):
        """Update document processing status"""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE documents 
                SET status = $2, 
                    chunk_count = COALESCE($3, chunk_count),
                    error_message = $4,
                    indexed_at = CASE WHEN $2 = 'indexed' THEN NOW() ELSE indexed_at END,
                    updated_at = NOW()
                WHERE id = $1
            """, document_id, status, chunk_count, error_message)
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1",
                document_id
            )
            return dict(row) if row else None
    
    async def list_documents(
        self,
        connection_id: str = None,
        status: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List documents with filtering"""
        conditions = []
        values = []
        param_idx = 1
        
        if connection_id:
            conditions.append(f"connection_id = ${param_idx}")
            values.append(connection_id)
            param_idx += 1
        
        if status:
            conditions.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        values.extend([limit, offset])
        
        query = f"""
            SELECT * FROM documents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
            return [dict(row) for row in rows]
    
    # ─────────────────────────────────────────────────────────────────────────
    # CHUNKS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def create_chunks(
        self,
        document_id: str,
        chunks: List[Dict[str, Any]]
    ) -> int:
        """Bulk insert chunks"""
        async with self._pool.acquire() as conn:
            # Prepare data
            records = [
                (
                    document_id,
                    chunk["index"],
                    chunk["content"],
                    chunk.get("token_count"),
                    chunk.get("start_char"),
                    chunk.get("end_char"),
                    chunk.get("page_number"),
                    chunk.get("section_title"),
                    chunk.get("vector_id")
                )
                for chunk in chunks
            ]
            
            await conn.executemany("""
                INSERT INTO chunks 
                    (document_id, chunk_index, content, token_count,
                     start_char, end_char, page_number, section_title, vector_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, records)
            
            return len(records)
    
    async def delete_chunks_by_document(self, document_id: str):
        """Delete all chunks for a document"""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM chunks WHERE document_id = $1",
                document_id
            )
