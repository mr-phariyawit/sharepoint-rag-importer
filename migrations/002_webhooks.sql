-- Webhook Subscriptions Table
-- Add this to init.sql or run as a migration

-- ============================================================================
-- WEBHOOK SUBSCRIPTIONS TABLE
-- Stores Microsoft Graph webhook subscriptions for real-time sync
-- ============================================================================
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id VARCHAR(255) PRIMARY KEY,  -- Microsoft subscription ID
    connection_id UUID NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    
    -- Subscription details
    resource TEXT NOT NULL,  -- Graph API resource path
    change_type VARCHAR(100) DEFAULT 'created,updated,deleted',
    notification_url TEXT,
    
    -- State
    client_state VARCHAR(64),  -- For validation
    expiration TIMESTAMPTZ NOT NULL,
    
    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- active, expired, error
    last_notification_at TIMESTAMPTZ,
    notification_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhook_subs_connection ON webhook_subscriptions(connection_id);
CREATE INDEX idx_webhook_subs_expiration ON webhook_subscriptions(expiration);

-- ============================================================================
-- WEBHOOK NOTIFICATIONS LOG
-- Optional: Log all incoming notifications for debugging
-- ============================================================================
CREATE TABLE IF NOT EXISTS webhook_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id VARCHAR(255) REFERENCES webhook_subscriptions(id) ON DELETE SET NULL,
    
    -- Notification details
    change_type VARCHAR(50),
    resource TEXT,
    resource_data JSONB,
    
    -- Processing
    processed_at TIMESTAMPTZ,
    processing_result VARCHAR(50),  -- success, error, skipped
    error_message TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhook_notif_sub ON webhook_notifications(subscription_id);
CREATE INDEX idx_webhook_notif_created ON webhook_notifications(created_at DESC);

-- ============================================================================
-- CLEANUP FUNCTION
-- Automatically clean up expired subscriptions
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_expired_subscriptions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM webhook_subscriptions
    WHERE expiration < NOW() - INTERVAL '7 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- UPDATE TRIGGER
-- ============================================================================
CREATE TRIGGER update_webhook_subscriptions_updated_at
    BEFORE UPDATE ON webhook_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
