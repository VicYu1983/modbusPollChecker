CREATE TABLE network_batches_v2 (
    id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('network_only', 'network_and_port', 'full_stack', 'mixed')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    device_names_json TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    max_concurrency INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    completed_device_count INTEGER NOT NULL DEFAULT 0,
    pass_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    timeout_count INTEGER NOT NULL DEFAULT 0,
    config_error_count INTEGER NOT NULL DEFAULT 0,
    partial_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

INSERT INTO network_batches_v2 SELECT * FROM network_batches;
DROP TABLE network_batches;
ALTER TABLE network_batches_v2 RENAME TO network_batches;
CREATE INDEX idx_network_batches_site_started
    ON network_batches(site_name, started_at DESC);