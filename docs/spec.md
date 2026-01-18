# SharePoint RAG Importer - Specification

## 1. Overview
The **SharePoint RAG Importer** is a system designed to import files from SharePoint and OneDrive into a Vector Database to enable Retrieval-Augmented Generation (RAG) capabilities. It provides recursive folder crawling, text extraction, chunking, embedding, and incremental synchronization.

## 2. Core Features

### 2.1 File Import
- **Recursive Crawling**: Traverse SharePoint folder structures.
- **File Support**: PDF, DOCX, XLSX, PPTX, TXT, CSV, MD, HTML, JSON.
- **Filtering**: Include/exclude by file type and size (max limit).
- **Metadata**: Capture path, size, mime_type, web_url, content_hash.

### 2.2 Vector Pipeline
- **Extraction**: Extract text from supported formats.
- **Chunking**: Split text into overlapping chunks (default 1000 tokens).
- **Embedding**: Generate vector embeddings (model agnostic, currently OpenAI/Cohere via config).
- **Storage**: Store vectors in **Qdrant** with metadata payloads.

### 2.3 Management API
- **Connections**: Manage SharePoint credentials (Tenant ID, Client ID, Secret).
- **Import Jobs**: Trigger imports, track progress, view stats.
- **Sync**: (Planned) Webhooks for real-time updates.

## 3. Architecture

### 3.1 Services
- **API Service** (FastAPI): Handles REST endpoints, connection management, and job triggering.
- **Worker/Background Task**: Handles long-running import jobs (crawling, processing).
- **Vector Store** (Qdrant): Stores embeddings and chunks.
- **Metadata Store** (PostgreSQL): Stores connections, job history, and document metadata.

### 3.2 Data Models

#### Connection
- `id`: UUID
- `name`: string
- `tenant_id`: string
- `client_id`: string
- `client_secret`: string (ENCRYPTED)
- `status`: connected | error

#### ImportJob
- `id`: UUID
- `connection_id`: UUID
- `status`: pending | crawling | processing | completed | failed
- `stats`: total_files, processed, failed

## 4. Security
- **Credential Storage**: SharePoint Client Secrets MUST be encrypted at rest in the database.
- **Access Control**: (Future) API Key authentication for the Importer API.

## 5. Current Gaps & Roadmap

### Completed
- [x] **Encryption**: `client_secret` encrypted with Fernet (SECURITY_KEY)
- [x] **Metadata Methods**: `list_import_jobs` and cascade `delete_connection` implemented
- [x] **Webhooks**: Full implementation - validation, renewals, delta processing
- [x] **Rate Limiting**: Tenacity retry with exponential backoff
- [x] **Frontend Dashboard**: Connections CRUD, Import Jobs monitoring, SharePoint browser

### Remaining (Phase 3 Search)
- [ ] **Hybrid Search**: Mode parameter accepted but only semantic implemented
- [ ] **Keyword Search**: Sparse vectors/BM25 not yet implemented
- [ ] **Date Range Filters**: Model defined but not connected to query
