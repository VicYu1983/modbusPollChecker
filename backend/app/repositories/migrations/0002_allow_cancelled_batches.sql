CREATE TABLE check_batches_v2 (
    id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('single', 'full')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    device_names_json TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    note TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    pass_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    timeout_count INTEGER NOT NULL DEFAULT 0,
    config_error_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

INSERT INTO check_batches_v2 (
    id, site_name, mode, status, device_names_json, config_snapshot_json,
    note, started_at, completed_at, pass_count, fail_count, timeout_count,
    config_error_count, unknown_count, error_message
)
SELECT
    id, site_name, mode, status, device_names_json, config_snapshot_json,
    note, started_at, completed_at, pass_count, fail_count, timeout_count,
    config_error_count, unknown_count, error_message
FROM check_batches;

DROP TABLE check_batches;
ALTER TABLE check_batches_v2 RENAME TO check_batches;
CREATE INDEX idx_batches_site_started ON check_batches(site_name, started_at DESC);