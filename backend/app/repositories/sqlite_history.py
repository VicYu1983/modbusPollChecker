from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..domain.models import BatchCounts, BatchStatus, CheckBatch, CheckRecord, SiteBaseline
from ..domain.network_models import (
    NetworkBatch,
    NetworkBatchCounts,
    NetworkBatchStatus,
    NetworkCheckRecord,
)
from ..ports.history import (
    BatchIsBaselineError,
    BatchNotDeletableError,
    BatchNotFoundError,
)
from ..schemas import CheckResult, DeviceConfig, NetworkCheckResult, SiteConfig


class SqliteHistoryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.migrations_path = Path(__file__).parent / "migrations"

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(self.migrations_path.glob("[0-9]*.sql")):
                version = int(migration.stem.split("_", 1)[0])
                if version in applied:
                    continue
                connection.execute("PRAGMA foreign_keys = OFF")
                try:
                    connection.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + migration.read_text(encoding="utf-8")
                        + "\nINSERT INTO schema_migrations(version, applied_at) VALUES ("
                        + str(version)
                        + ", '"
                        + datetime.now(timezone.utc).isoformat()
                        + "');\nCOMMIT;"
                    )
                finally:
                    connection.execute("PRAGMA foreign_keys = ON")
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise sqlite3.IntegrityError("database migration broke foreign keys")

    def create_batch(self, batch: CheckBatch) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO check_batches (
                    id, site_name, mode, status, device_names_json,
                    config_snapshot_json, note, started_at, completed_at,
                    pass_count, fail_count, timeout_count, config_error_count,
                    unknown_count, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch.id,
                    batch.site_name,
                    batch.mode,
                    batch.status,
                    json.dumps(batch.device_names, ensure_ascii=False),
                    batch.config_snapshot.model_dump_json(),
                    batch.note,
                    batch.started_at.isoformat(),
                    batch.completed_at.isoformat() if batch.completed_at else None,
                    batch.pass_count,
                    batch.fail_count,
                    batch.timeout_count,
                    batch.config_error_count,
                    batch.unknown_count,
                    batch.error_message,
                ),
            )

    def update_batch_status(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        completed_at: datetime | None = None,
        counts: BatchCounts | None = None,
        error_message: str | None = None,
    ) -> None:
        values = counts or BatchCounts()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE check_batches SET status = ?, completed_at = ?,
                    pass_count = ?, fail_count = ?, timeout_count = ?,
                    config_error_count = ?, unknown_count = ?, error_message = ?
                    WHERE id = ?""",
                (
                    status,
                    completed_at.isoformat() if completed_at else None,
                    values.pass_count,
                    values.fail_count,
                    values.timeout_count,
                    values.config_error_count,
                    values.unknown_count,
                    error_message,
                    batch_id,
                ),
            )
            if cursor.rowcount == 0:
                raise BatchNotFoundError(batch_id)

    def get_batch(self, batch_id: str) -> CheckBatch:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM check_batches WHERE id = ?", (batch_id,)
            ).fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        return self._batch_from_row(row)

    def list_batches(
        self,
        site_name: str | None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[CheckBatch], int]:
        where = " WHERE site_name = ?" if site_name else ""
        parameters: tuple[object, ...] = (site_name,) if site_name else ()
        with self._connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM check_batches" + where, parameters
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM check_batches"
                + where
                + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
        return [self._batch_from_row(row) for row in rows], total

    def delete_batch(self, batch_id: str) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM check_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if row is None:
                raise BatchNotFoundError(batch_id)
            baseline = connection.execute(
                "SELECT 1 FROM site_baselines WHERE baseline_batch_id = ? LIMIT 1",
                (batch_id,),
            ).fetchone()
            if baseline is not None:
                raise BatchIsBaselineError("目前基準批次不可刪除，請先清除基準")
            if row["status"] in {"pending", "running"}:
                raise BatchNotDeletableError("執行中的批次不可刪除")
            connection.execute("DELETE FROM check_records WHERE batch_id = ?", (batch_id,))
            connection.execute("DELETE FROM check_batches WHERE id = ?", (batch_id,))

    def save_record(self, record: CheckRecord) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO check_records (
                    batch_id, device_name, result_json, device_snapshot_json
                ) VALUES (?, ?, ?, ?)""",
                (
                    record.batch_id,
                    record.result.device_name,
                    record.result.model_dump_json(),
                    record.device_snapshot.model_dump_json(),
                ),
            )

    def create_network_batch(self, batch: NetworkBatch) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO network_batches (
                    id, site_name, mode, status, device_names_json,
                    config_snapshot_json, max_concurrency, started_at, completed_at,
                    completed_device_count, pass_count, fail_count, timeout_count,
                    config_error_count, partial_count, unknown_count, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch.id,
                    batch.site_name,
                    batch.mode,
                    batch.status,
                    json.dumps(batch.device_names, ensure_ascii=False),
                    batch.config_snapshot.model_dump_json(),
                    batch.max_concurrency,
                    batch.started_at.isoformat(),
                    batch.completed_at.isoformat() if batch.completed_at else None,
                    batch.completed_device_count,
                    batch.pass_count,
                    batch.fail_count,
                    batch.timeout_count,
                    batch.config_error_count,
                    batch.partial_count,
                    batch.unknown_count,
                    batch.error_message,
                ),
            )

    def update_network_batch_status(
        self,
        batch_id: str,
        status: NetworkBatchStatus,
        *,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE network_batches SET status = ?, completed_at = ?, error_message = ?
                    WHERE id = ?""",
                (
                    status,
                    completed_at.isoformat() if completed_at else None,
                    error_message,
                    batch_id,
                ),
            )
            if cursor.rowcount == 0:
                raise BatchNotFoundError(batch_id)

    def get_network_batch(self, batch_id: str) -> NetworkBatch:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM network_batches WHERE id = ?", (batch_id,)
            ).fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        return self._network_batch_from_row(row)

    def list_network_batches(
        self,
        site_name: str | None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[NetworkBatch], int]:
        where = " WHERE site_name = ?" if site_name else ""
        parameters: tuple[object, ...] = (site_name,) if site_name else ()
        with self._connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM network_batches" + where, parameters
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM network_batches"
                + where
                + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
        return [self._network_batch_from_row(row) for row in rows], total

    def delete_network_batch(self, batch_id: str) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM network_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if row is None:
                raise BatchNotFoundError(batch_id)
            baseline = connection.execute(
                "SELECT 1 FROM device_check_baselines WHERE baseline_batch_id = ? LIMIT 1",
                (batch_id,),
            ).fetchone()
            if baseline is not None:
                raise BatchIsBaselineError("目前基準批次不可刪除，請先清除基準")
            if row["status"] in {"pending", "running"}:
                raise BatchNotDeletableError("執行中的批次不可刪除")
            connection.execute("DELETE FROM network_results WHERE batch_id = ?", (batch_id,))
            connection.execute("DELETE FROM network_batches WHERE id = ?", (batch_id,))

    def save_network_result(
        self,
        record: NetworkCheckRecord,
        counts: NetworkBatchCounts,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO network_results (
                    batch_id, device_name, result_json, device_snapshot_json
                ) VALUES (?, ?, ?, ?)""",
                (
                    record.batch_id,
                    record.result.device_name,
                    record.result.model_dump_json(),
                    record.device_snapshot.model_dump_json(),
                ),
            )
            cursor = connection.execute(
                """UPDATE network_batches SET completed_device_count = completed_device_count + 1,
                    pass_count = ?, fail_count = ?, timeout_count = ?,
                    config_error_count = ?, partial_count = ?, unknown_count = ?
                    WHERE id = ?""",
                (
                    counts.pass_count,
                    counts.fail_count,
                    counts.timeout_count,
                    counts.config_error_count,
                    counts.partial_count,
                    counts.unknown_count,
                    record.batch_id,
                ),
            )
            if cursor.rowcount == 0:
                raise BatchNotFoundError(record.batch_id)

    def list_network_results(self, batch_id: str) -> list[NetworkCheckRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM network_results WHERE batch_id = ? ORDER BY id",
                (batch_id,),
            ).fetchall()
        return [self._network_result_from_row(row) for row in rows]

    def set_device_check_baseline(self, site_name: str, batch_id: str) -> datetime:
        updated_at = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO device_check_baselines (site_name, baseline_batch_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(site_name) DO UPDATE SET
                    baseline_batch_id = excluded.baseline_batch_id,
                    updated_at = excluded.updated_at""",
                (site_name, batch_id, updated_at.isoformat()),
            )
        return updated_at

    def get_device_check_baseline(self, site_name: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT baseline_batch_id FROM device_check_baselines WHERE site_name = ?",
                (site_name,),
            ).fetchone()
        return row["baseline_batch_id"] if row else None

    def clear_device_check_baseline(self, site_name: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM device_check_baselines WHERE site_name = ?",
                (site_name,),
            )
        return cursor.rowcount > 0

    def list_records(self, batch_id: str) -> list[CheckRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM check_records WHERE batch_id = ? ORDER BY id",
                (batch_id,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def set_baseline(self, site_name: str, batch_id: str) -> SiteBaseline:
        updated_at = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO site_baselines (site_name, baseline_batch_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(site_name) DO UPDATE SET
                    baseline_batch_id = excluded.baseline_batch_id,
                    updated_at = excluded.updated_at""",
                (site_name, batch_id, updated_at.isoformat()),
            )
        return SiteBaseline(
            site_name=site_name,
            baseline_batch_id=batch_id,
            updated_at=updated_at,
        )

    def get_baseline(self, site_name: str) -> SiteBaseline | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM site_baselines WHERE site_name = ?",
                (site_name,),
            ).fetchone()
        if row is None:
            return None
        return SiteBaseline(
            site_name=row["site_name"],
            baseline_batch_id=row["baseline_batch_id"],
            updated_at=row["updated_at"],
        )

    def clear_baseline(self, site_name: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM site_baselines WHERE site_name = ?",
                (site_name,),
            )
        return cursor.rowcount > 0

    def fail_interrupted_batches(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            modbus_cursor = connection.execute(
                """UPDATE check_batches SET status = 'failed', completed_at = ?,
                    error_message = 'interrupted by shutdown'
                    WHERE status IN ('pending', 'running')""",
                (now,),
            )
            network_cursor = connection.execute(
                """UPDATE network_batches SET status = 'failed', completed_at = ?,
                    error_message = 'interrupted by shutdown'
                    WHERE status IN ('pending', 'running')""",
                (now,),
            )
        return modbus_cursor.rowcount + network_cursor.rowcount

    @staticmethod
    def _network_batch_from_row(row: sqlite3.Row) -> NetworkBatch:
        return NetworkBatch(
            id=row["id"],
            site_name=row["site_name"],
            mode=row["mode"],
            status=row["status"],
            device_names=json.loads(row["device_names_json"]),
            config_snapshot=SiteConfig.model_validate_json(row["config_snapshot_json"]),
            max_concurrency=row["max_concurrency"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            completed_device_count=row["completed_device_count"],
            pass_count=row["pass_count"],
            fail_count=row["fail_count"],
            timeout_count=row["timeout_count"],
            config_error_count=row["config_error_count"],
            partial_count=row["partial_count"],
            unknown_count=row["unknown_count"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _network_result_from_row(row: sqlite3.Row) -> NetworkCheckRecord:
        return NetworkCheckRecord(
            id=row["id"],
            batch_id=row["batch_id"],
            result=NetworkCheckResult.model_validate_json(row["result_json"]),
            device_snapshot=DeviceConfig.model_validate_json(row["device_snapshot_json"]),
        )

    @staticmethod
    def _batch_from_row(row: sqlite3.Row) -> CheckBatch:
        return CheckBatch(
            id=row["id"],
            site_name=row["site_name"],
            mode=row["mode"],
            status=row["status"],
            device_names=json.loads(row["device_names_json"]),
            config_snapshot=SiteConfig.model_validate_json(
                row["config_snapshot_json"]
            ),
            note=row["note"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            pass_count=row["pass_count"],
            fail_count=row["fail_count"],
            timeout_count=row["timeout_count"],
            config_error_count=row["config_error_count"],
            unknown_count=row["unknown_count"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> CheckRecord:
        return CheckRecord(
            id=row["id"],
            batch_id=row["batch_id"],
            result=CheckResult.model_validate_json(row["result_json"]),
            device_snapshot=DeviceConfig.model_validate_json(
                row["device_snapshot_json"]
            ),
        )