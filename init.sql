-- SharePoint RAG Importer - Database Schema
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CONNECTIONS TABLE
-- Stores SharePoint/OneDrive connection configurations
-- ============================================================================
CREATE TABLE connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    
    -- OAuth tokens (encrypted)
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMPTZ,
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending', -- pending, connected, error
    last_error TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_connections_status ON connections(status);

-- ============================================================================
-- IMPORT JOBS TABLE
-- Tracks folder import operations
-- ============================================================================
CREATE TABLE import_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connection_id UUID NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    
    -- Source info
    folder_url TEXT NOT NULL,
    folder_id VARCHAR(255),
    folder_name VARCHAR(500),
    site_id VARCHAR(255),
    drive_id VARCHAR(255),
    
    -- Options
    recursive BOOLEAN DEFAULT TRUE,
    file_types TEXT[] DEFAULT ARRAY['pdf', 'docx', 'xlsx', 'pptx', 'txt', 'csv', 'md'],
    
    -- Progress tracking
    status VARCHAR(50) DEFAULT 'pending', -- pending, crawling, processing, completed, failed
    total_files_found INTEGER DEFAULT 0,
    files_processed INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    current_file VARCHAR(500),
    
    -- Results
    total_chunks_created INTEGER DEFAULT 0,
    error_log JSONB DEFAULT '[]'::jsonb,
    
    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_import_jobs_connection ON import_jobs(connection_id);
CREATE INDEX idx_import_jobs_status ON import_jobs(status);

-- ============================================================================
-- DOCUMENTS TABLE
-- Stores metadata for imported documents
-- ============================================================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connection_id UUID NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    import_job_id UUID REFERENCES import_jobs(id) ON DELETE SET NULL,
    
    -- SharePoint identifiers
    sharepoint_id VARCHAR(255) NOT NULL,
    drive_id VARCHAR(255),
    site_id VARCHAR(255),
    
    -- File info
    name VARCHAR(500) NOT NULL,
    path TEXT NOT NULL,
    mime_type VARCHAR(100),
    size_bytes BIGINT,
    
    -- Content hash for change detection
    content_hash VARCHAR(64),
    etag VARCHAR(255),
    
    -- SharePoint metadata
    web_url TEXT,
    created_by VARCHAR(255),
    modified_by VARCHAR(255),
    sharepoint_created_at TIMESTAMPTZ,
    sharepoint_modified_at TIMESTAMPTZ,
    
    -- Processing status
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, indexed, failed
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- Timestamps
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(connection_id, sharepoint_id)
);

CREATE INDEX idx_documents_connection ON documents(connection_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_path ON documents(path);
CREATE INDEX idx_documents_sharepoint_id ON documents(sharepoint_id);

-- ============================================================================
-- CHUNKS TABLE
-- Stores chunk metadata (vectors stored in Qdrant)
-- ============================================================================
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Chunk info
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    
    -- Position in document
    start_char INTEGER,
    end_char INTEGER,
    page_number INTEGER,
    section_title VARCHAR(500),
    
    -- Vector reference
    vector_id VARCHAR(255), -- ID in Qdrant
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_vector_id ON chunks(vector_id);

-- ============================================================================
-- QUERY HISTORY TABLE
-- Logs queries for analytics
-- ============================================================================
CREATE TABLE query_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Query info
    query_text TEXT NOT NULL,
    
    -- Results
    chunks_retrieved INTEGER,
    response_text TEXT,
    sources JSONB,
    
    -- Performance
    retrieval_time_ms INTEGER,
    generation_time_ms INTEGER,
    total_time_ms INTEGER,
    
    -- Tokens
    embedding_tokens INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_query_history_created ON query_history(created_at DESC);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER update_connections_updated_at
    BEFORE UPDATE ON connections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Import job summary
CREATE VIEW import_job_summary AS
SELECT 
    j.id,
    j.connection_id,
    c.name as connection_name,
    j.folder_name,
    j.status,
    j.total_files_found,
    j.files_processed,
    j.files_failed,
    j.total_chunks_created,
    ROUND(
        CASE WHEN j.total_files_found > 0 
        THEN (j.files_processed::numeric / j.total_files_found * 100) 
        ELSE 0 END, 
        2
    ) as progress_percent,
    j.started_at,
    j.completed_at,
    j.created_at,
    EXTRACT(EPOCH FROM (COALESCE(j.completed_at, NOW()) - j.started_at)) as duration_seconds
FROM import_jobs j
JOIN connections c ON j.connection_id = c.id;

-- Document statistics by connection
CREATE VIEW connection_stats AS
SELECT 
    c.id as connection_id,
    c.name as connection_name,
    c.status,
    COUNT(DISTINCT d.id) as total_documents,
    COUNT(DISTINCT CASE WHEN d.status = 'indexed' THEN d.id END) as indexed_documents,
    SUM(d.chunk_count) as total_chunks,
    SUM(d.size_bytes) as total_size_bytes,
    MAX(d.indexed_at) as last_indexed_at
FROM connections c
LEFT JOIN documents d ON c.id = d.connection_id
GROUP BY c.id, c.name, c.status;

-- ============================================================================
-- SAMPLE DATA (Optional - comment out in production)
-- ============================================================================

-- ============================================================================
-- USERS & AUTH TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT DEFAULT 'user', -- user, admin
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    permissions TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    use_count INTEGER DEFAULT 0,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
