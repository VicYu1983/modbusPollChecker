CREATE TABLE device_check_baselines (
    site_name TEXT PRIMARY KEY,
    baseline_batch_id TEXT NOT NULL REFERENCES network_batches(id) ON DELETE RESTRICT,
    updated_at TEXT NOT NULL
);
