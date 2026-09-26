CREATE TABLE check_batches (
    id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('single', 'full')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
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

CREATE TABLE check_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES check_batches(id) ON DELETE RESTRICT,
    device_name TEXT NOT NULL,
    result_json TEXT NOT NULL,
    device_snapshot_json TEXT NOT NULL
);

CREATE INDEX idx_records_batch ON check_records(batch_id);
CREATE INDEX idx_batches_site_started ON check_batches(site_name, started_at DESC);

CREATE TABLE site_baselines (
    site_name TEXT PRIMARY KEY,
    baseline_batch_id TEXT NOT NULL REFERENCES check_batches(id) ON DELETE RESTRICT,
    updated_at TEXT NOT NULL
);