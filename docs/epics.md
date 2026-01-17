# Epics & User Journeys

This document breaks down the project roadmap into granular Epics, User Journeys, and Tasks.

## 🚧 Phase 2: Reliability & Sync

### Epic: Real-time Data Synchronization
**Goal**: Keep the vector index in sync with SharePoint automatically using Webhooks.

#### Journey: Configuring Webhooks
> As an admin, I want to subscribe to SharePoint change notifications so that my index stays fresh.
- [ ] **Task**: Research Microsoft Graph subscription API requirements (expiration time, validation handshake).
- [ ] **Task**: Implement `POST /api/webhooks` endpoint to handle the validation handshake.
- [ ] **Task**: Implement logic to renew subscriptions automatically (they expire every ~3 days).
- [ ] **Task**: Store subscription IDs in `MetadataStore`.

#### Journey: Processing Delta Changes
> As a system, I want to process change notifications efficiently so that I don't re-crawl the entire library.
- [ ] **Task**: Parse incoming webhook notifications (resource data).
- [ ] **Task**: Query Microosoft Graph `/delta` endpoint using `deltaToken` to get specific changes.
- [ ] **Task**: Handle **File Added**: Trigger single file import.
- [ ] **Task**: Handle **File Updated**: Re-process and re-index file (delete old chunks).
- [ ] **Task**: Handle **File Deleted**: Trigger cascade delete for specific document.

### Epic: System Resilience
**Goal**: Manage API limits and failures gracefully.

#### Journey: Handling Rate Limits
> As a system, I want to handle 429 Too Many Requests errors so that the import doesn't crash.
- [ ] **Task**: Integrate `tenacity` retry decorator on `SharePointClient` methods.
- [ ] **Task**: Implement exponential backoff strategy for Graph API calls.

## 🔮 Phase 3: Search & Intelligence

### Epic: Advanced Retrieval
**Goal**: Provide high-quality search results.

#### Journey: Performing Hybrid Search
> As a user, I want to search using both keywords and meaning so that I find exact matches and conceptual matches.
- [ ] **Task**: Research Qdrant hybrid search capabilities (sparse vectors or payload filtering).
- [ ] **Task**: Implement `POST /api/search` endpoint accepting `query` and `mode` (hybrid/semantic/keyword).
- [ ] **Task**: Implement keyword extraction (or sparse embedding generation) for the keyword component.

#### Journey: Filtering Results
> As a user, I want to filter results by specific folders or file types.
- [ ] **Task**: Update `SearchRequest` model to include `filters` (file_type, date_range).
- [ ] **Task**: Map API filters to Qdrant payload filters.

## 🎨 Phase 4: Frontend Dashboard

### Epic: Administration UI
**Goal**: Visual management of the system.

#### Journey: Managing Connections
> As an admin, I want a web UI to verify and delete connections.
- [ ] **Task**: Create `frontend/` React/Vite project.
- [ ] **Task**: Build "Connections" page listing all active connections with status indicators.
- [ ] **Task**: Add "Test Connection" button calling the API.

#### Journey: Monitoring Imports
> As an admin, I want to see a progress bar for running imports.
- [ ] **Task**: Build "Import Jobs" page with a real-time polling hook to `GET /api/import/{id}`.
- [ ] **Task**: specific visual indicators for "Failed" files with error logs.
