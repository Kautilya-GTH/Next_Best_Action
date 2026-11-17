-- SQLite schema for nbc-mvp. Idempotent: safe to run on every start.

-- Raw inputs, loaded from CSV for inspection and ad-hoc SQL.
CREATE TABLE IF NOT EXISTS accounts (
    account_id       TEXT PRIMARY KEY,
    owner_id         TEXT NOT NULL,
    arr              REAL,
    days_to_renewal  INTEGER,
    usage_score      REAL CHECK (usage_score IS NULL OR usage_score BETWEEN 0 AND 100),
    active_users     INTEGER,
    seats_purchased  INTEGER,
    region           TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    account_id   TEXT NOT NULL,
    signal_name  TEXT NOT NULL,
    value        TEXT,            -- stored raw; parsed by kind at scoring time
    PRIMARY KEY (account_id, signal_name)
);

-- Owner feedback. Any row for an account excludes it from future digests.
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    owner_id    TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('taken', 'not_applicable')),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL      -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_feedback_account ON feedback (account_id);

-- Accounts excluded from all owners' digests (exclusion is per account).
CREATE VIEW IF NOT EXISTS v_excluded_accounts AS
SELECT DISTINCT account_id FROM feedback;

-- Derived seat utilization in percent, capped at 100; 0 when no seats.
CREATE VIEW IF NOT EXISTS v_account_features AS
SELECT
    account_id,
    owner_id,
    arr,
    days_to_renewal,
    usage_score,
    CASE
        WHEN seats_purchased IS NULL OR seats_purchased <= 0 OR active_users IS NULL THEN 0.0
        ELSE MIN(100.0, 100.0 * active_users / seats_purchased)
    END AS seat_utilization
FROM accounts;
