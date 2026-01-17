-- Authentication Tables
-- Add this to init.sql or run as a migration

-- ============================================================================
-- USERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Credentials
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    
    -- Profile
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    
    -- Role & Status
    role VARCHAR(50) DEFAULT 'user',  -- user, admin
    status VARCHAR(50) DEFAULT 'active',  -- active, inactive, suspended
    
    -- Email verification
    email_verified BOOLEAN DEFAULT FALSE,
    email_verification_token VARCHAR(255),
    email_verified_at TIMESTAMPTZ,
    
    -- Password reset
    password_reset_token VARCHAR(255),
    password_reset_expires_at TIMESTAMPTZ,
    
    -- Activity tracking
    last_login_at TIMESTAMPTZ,
    last_login_ip VARCHAR(45),
    login_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);

-- ============================================================================
-- API KEYS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
    -- Key info
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hash
    key_prefix VARCHAR(20) NOT NULL,  -- First chars for identification
    
    -- Permissions
    permissions TEXT[] DEFAULT ARRAY['read', 'write'],
    
    -- Scope (optional - limit to specific connections)
    connection_ids UUID[],
    
    -- Expiration
    expires_at TIMESTAMPTZ,
    
    -- Revocation
    revoked_at TIMESTAMPTZ,
    revoked_by UUID REFERENCES users(id),
    revoke_reason TEXT,
    
    -- Usage tracking
    last_used_at TIMESTAMPTZ,
    last_used_ip VARCHAR(45),
    use_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_expires ON api_keys(expires_at);

-- ============================================================================
-- USER SESSIONS TABLE (Optional - for session-based auth)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session token
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    
    -- Device/client info
    user_agent TEXT,
    ip_address VARCHAR(45),
    device_name VARCHAR(255),
    
    -- Expiration
    expires_at TIMESTAMPTZ NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_token ON user_sessions(token_hash);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at);

-- ============================================================================
-- AUDIT LOG TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Actor
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    ip_address VARCHAR(45),
    
    -- Action
    action VARCHAR(100) NOT NULL,  -- login, logout, create_connection, import, query, etc.
    resource_type VARCHAR(100),  -- connection, import_job, document, etc.
    resource_id UUID,
    
    -- Details
    details JSONB,
    
    -- Result
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

-- ============================================================================
-- NOTIFICATION PREFERENCES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Email notifications
    email_import_complete BOOLEAN DEFAULT TRUE,
    email_import_failed BOOLEAN DEFAULT TRUE,
    email_weekly_summary BOOLEAN DEFAULT FALSE,
    
    -- Webhook notifications
    webhook_url TEXT,
    webhook_secret VARCHAR(64),
    webhook_enabled BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Update trigger for users
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Update trigger for notification preferences
CREATE TRIGGER update_notification_prefs_updated_at
    BEFORE UPDATE ON notification_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- DEFAULT ADMIN USER (Optional - remove in production)
-- ============================================================================
-- Password: admin123 (change immediately!)
-- INSERT INTO users (email, password_hash, name, role, email_verified)
-- VALUES (
--     'admin@example.com',
--     'a1b2c3d4e5f6:hashed_password_here',
--     'Administrator',
--     'admin',
--     TRUE
-- );
