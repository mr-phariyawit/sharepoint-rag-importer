# SharePoint RAG Importer - Roadmap

This document correlates with `docs/spec.md` and tracks the strategic development of the project.

## ✅ Phase 1: Foundation (Completed)
**Goal**: Establish the core infrastructure for secure connection and data import.
- [x] **Project Setup**: Antigravity structure, Docker configuration.
- [x] **Security**: Encrypted storage for SharePoint Client Secrets (`EncryptionService`).
- [x] **Metadata Store**: PostgreSQL schema for connections, jobs, documents, and chunks.
- [x] **Core API**:
    - Manage Connections (`create`, `delete` with cascade).
    - Import Jobs (`start`, `list`, `monitor`).
- [x] **Vector Store**: Qdrant integration for embedding storage.

## 🚧 Phase 2: Reliability & Sync (Current Focus)
**Goal**: Ensure data consistency and real-time updates.
- [ ] **Real-time Webhooks**: Handle SharePoint delta changes (add/update/delete notifications).
- [ ] **Resilience**: Implement robust retries for API rate limits (Graph API throtling).
- [ ] **Background Workers**: Optimize Celery/RQ task queues for large imports.
- [ ] **Observability**: Structured logging and metrics (Prometheus).

## 🔮 Phase 3: Search & Intelligence
**Goal**: Unlock the value of indexed data through powerful retrieval.
- [ ] **Hybrid Search API**: Combine vector similarity (semantic) with keyword search (BM25).
- [ ] **Advanced Filtering**: Faceted search by date, author, file type.
- [ ] **RAG Endpoint**: Direct "Chat with Documents" API using OpenAI/Anthropic.
- [ ] **Citations**: Return precise source text locations with search results.

## 🎨 Phase 4: Frontend Dashboard
**Goal**: Provide a user-friendly interface for administration.
- [ ] **Connection Manager**: UI to add/remove SharePoint connections.
- [ ] **Job Monitor**: Real-time progress bars for active imports.
- [ ] **Document Browser**: View indexed files and their chunks.
- [ ] **Search Playground**: Test and tune search results.
