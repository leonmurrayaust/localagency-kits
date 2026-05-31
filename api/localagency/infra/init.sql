-- LocalAgency Kits — Database Schema (PostgreSQL 15+)
-- Run on first startup via docker-entrypoint-initdb.d

-- ── Client Profiles ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS client_profiles (
    client_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name   TEXT NOT NULL,
    vertical        TEXT NOT NULL DEFAULT 'other',
    address         TEXT DEFAULT '',
    phone           TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    service_area    TEXT DEFAULT 'Phoenix Metro Area',

    -- Brand voice (JSONB for flexible schema)
    brand_voice     JSONB DEFAULT '{}',
    operating_hours JSONB DEFAULT '{}',
    service_catalog JSONB DEFAULT '{}',

    -- Integration tokens (encrypted at rest in production)
    twilio_phone_sid    TEXT DEFAULT NULL,
    stripe_customer_id  TEXT DEFAULT NULL,
    calendly_link       TEXT DEFAULT NULL,

    -- Billing
    subscription_status TEXT DEFAULT 'trialing'
                        CHECK (subscription_status IN ('trialing', 'active', 'past_due', 'canceled')),
    subscription_id     TEXT DEFAULT NULL,
    mrr                 NUMERIC(10,2) DEFAULT 497.00,

    -- Preferences
    social_auto_approve BOOLEAN DEFAULT FALSE,
    booking_sms_confirm BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    onboarded_at    TIMESTAMPTZ DEFAULT NULL,
    is_active       BOOLEAN DEFAULT TRUE
);

-- ── Call Events (VoiceKit) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS call_events (
    id              BIGSERIAL PRIMARY KEY,
    call_sid        TEXT NOT NULL UNIQUE,
    client_id       UUID REFERENCES client_profiles(client_id),
    from_number     TEXT NOT NULL,
    to_number       TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'inbound_call',
    intent          TEXT DEFAULT NULL,
    transcript      TEXT DEFAULT NULL,
    booking_made    BOOLEAN DEFAULT FALSE,
    booking_ref     TEXT DEFAULT NULL,
    escalated       BOOLEAN DEFAULT FALSE,
    duration_seconds INTEGER DEFAULT NULL,
    api_cost        NUMERIC(10,4) DEFAULT 0.0,
    error           TEXT DEFAULT NULL,
    trace_id        TEXT DEFAULT '',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ DEFAULT NULL
);

-- Partition by month for 90-day retention
CREATE INDEX idx_call_events_client ON call_events(client_id, started_at DESC);
CREATE INDEX idx_call_events_state ON call_events(state);

-- ── Booking Events ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS booking_events (
    id              BIGSERIAL PRIMARY KEY,
    booking_ref     TEXT NOT NULL UNIQUE,
    call_sid        TEXT REFERENCES call_events(call_sid),
    client_id       UUID REFERENCES client_profiles(client_id),
    service_name    TEXT DEFAULT '',
    scheduled_date  TIMESTAMPTZ,
    caller_name     TEXT DEFAULT '',
    caller_phone    TEXT DEFAULT '',
    status          TEXT DEFAULT 'confirmed'
                    CHECK (status IN ('confirmed', 'completed', 'canceled', 'no_show')),
    sms_sent        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Dead Letter Queue ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dlq_events (
    dlq_entry_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id     TEXT NOT NULL,
    source_agent    TEXT NOT NULL,
    target_agent    TEXT NOT NULL,
    original_envelope_id TEXT DEFAULT NULL,
    max_attempts    INTEGER DEFAULT 3,
    attempts_made   INTEGER DEFAULT 0,
    last_error      TEXT DEFAULT '',
    error_chain     JSONB DEFAULT '[]',
    payload_snapshot JSONB DEFAULT '{}',
    trace_id        TEXT DEFAULT '',
    client_id       UUID REFERENCES client_profiles(client_id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    replayed        BOOLEAN DEFAULT FALSE,
    replay_count    INTEGER DEFAULT 0,
    resolved        BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT DEFAULT ''
);

CREATE INDEX idx_dlq_unresolved ON dlq_events(resolved, created_at DESC);
CREATE INDEX idx_dlq_client ON dlq_events(client_id);

-- ── Circuit Breaker State ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS circuit_breaker_state (
    agent_name      TEXT PRIMARY KEY,
    state           TEXT NOT NULL DEFAULT 'CLOSED'
                    CHECK (state IN ('CLOSED', 'OPEN', 'HALF_OPEN')),
    failure_count   INTEGER DEFAULT 0,
    last_failure_at TIMESTAMPTZ DEFAULT NULL,
    window_start    TIMESTAMPTZ DEFAULT NOW(),
    last_state_change TIMESTAMPTZ DEFAULT NOW(),
    cooldown_until  TIMESTAMPTZ DEFAULT NULL,
    config_json     JSONB DEFAULT '{}'  -- threshold, window_seconds, cooldown_seconds
);

-- ── Alert / Escalation Events ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS escalation_events (
    emergency_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity        TEXT NOT NULL CHECK (severity IN ('P0', 'P1', 'P2', 'P3', 'P4')),
    agent           TEXT NOT NULL,
    client_id       UUID REFERENCES client_profiles(client_id),
    error_detail    TEXT DEFAULT '',
    context_json    JSONB DEFAULT '{}',
    trace_id        TEXT DEFAULT '',
    acknowledged    BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ DEFAULT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_escalation_severity ON escalation_events(severity, acknowledged, created_at DESC);

-- ── Active Clients View ─────────────────────────────────────────────────────
CREATE VIEW active_clients AS
SELECT * FROM client_profiles
WHERE is_active = TRUE
  AND subscription_status IN ('trialing', 'active');
