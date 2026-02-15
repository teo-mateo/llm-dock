import json
import sqlite3
import logging
from typing import Optional, List, Tuple

from .models import BenchmarkRun

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id           TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    model_path   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    params_json  TEXT NOT NULL DEFAULT '{}',
    pp_avg_ts    REAL,
    pp_stddev_ts REAL,
    tg_avg_ts    REAL,
    tg_stddev_ts REAL,
    raw_output    TEXT,
    error_message TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at   TEXT,
    completed_at TEXT,
    build_commit TEXT,
    model_type   TEXT,
    model_size   INTEGER,
    model_n_params INTEGER,
    gpu_info     TEXT,
    cpu_info     TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_service ON benchmark_runs(service_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON benchmark_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON benchmark_runs(created_at);
"""


class BenchmarkDB:
    def __init__(self, db_path: str = "benchmarks.db"):
        self.db_path = db_path
        self._persistent_conn = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _close_conn(self, conn: sqlite3.Connection):
        if conn is not self._persistent_conn:
            conn.close()

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            self._close_conn(conn)

    def _row_to_run(self, row: sqlite3.Row) -> BenchmarkRun:
        params = json.loads(row["params_json"]) if row["params_json"] else {}
        return BenchmarkRun(
            id=row["id"],
            service_name=row["service_name"],
            model_path=row["model_path"],
            status=row["status"],
            params_json=params,
            pp_avg_ts=row["pp_avg_ts"],
            pp_stddev_ts=row["pp_stddev_ts"],
            tg_avg_ts=row["tg_avg_ts"],
            tg_stddev_ts=row["tg_stddev_ts"],
            raw_output=row["raw_output"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            build_commit=row["build_commit"],
            model_type=row["model_type"],
            model_size=row["model_size"],
            model_n_params=row["model_n_params"],
            gpu_info=row["gpu_info"],
            cpu_info=row["cpu_info"],
        )

    def create_run(self, run: BenchmarkRun) -> BenchmarkRun:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO benchmark_runs
                   (id, service_name, model_path, status, params_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.service_name,
                    run.model_path,
                    run.status,
                    json.dumps(run.params_json),
                ),
            )
            conn.commit()
            return self.get_run(run.id)
        finally:
            self._close_conn(conn)

    def get_run(self, run_id: str) -> Optional[BenchmarkRun]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM benchmark_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_run(row)
        finally:
            self._close_conn(conn)

    def list_runs(
        self,
        service_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[BenchmarkRun], int]:
        conn = self._get_conn()
        try:
            conditions = []
            params = []

            if service_name:
                conditions.append("service_name = ?")
                params.append(service_name)
            if status:
                conditions.append("status = ?")
                params.append(status)

            where = ""
            if conditions:
                where = "WHERE " + " AND ".join(conditions)

            total = conn.execute(
                f"SELECT COUNT(*) FROM benchmark_runs {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"SELECT * FROM benchmark_runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

            runs = [self._row_to_run(row) for row in rows]
            return runs, total
        finally:
            self._close_conn(conn)

    def update_status(
        self,
        run_id: str,
        status: str,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        conn = self._get_conn()
        try:
            fields = ["status = ?"]
            params = [status]

            if started_at:
                fields.append("started_at = ?")
                params.append(started_at)
            if completed_at:
                fields.append("completed_at = ?")
                params.append(completed_at)
            if error_message is not None:
                fields.append("error_message = ?")
                params.append(error_message)

            params.append(run_id)
            conn.execute(
                f"UPDATE benchmark_runs SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    def update_results(
        self,
        run_id: str,
        pp_avg_ts: Optional[float] = None,
        pp_stddev_ts: Optional[float] = None,
        tg_avg_ts: Optional[float] = None,
        tg_stddev_ts: Optional[float] = None,
        raw_output: Optional[str] = None,
        build_commit: Optional[str] = None,
        model_type: Optional[str] = None,
        model_size: Optional[int] = None,
        model_n_params: Optional[int] = None,
        gpu_info: Optional[str] = None,
        cpu_info: Optional[str] = None,
    ):
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE benchmark_runs SET
                   pp_avg_ts = ?, pp_stddev_ts = ?,
                   tg_avg_ts = ?, tg_stddev_ts = ?,
                   raw_output = ?,
                   build_commit = ?, model_type = ?,
                   model_size = ?, model_n_params = ?,
                   gpu_info = ?, cpu_info = ?
                   WHERE id = ?""",
                (
                    pp_avg_ts, pp_stddev_ts,
                    tg_avg_ts, tg_stddev_ts,
                    raw_output,
                    build_commit, model_type,
                    model_size, model_n_params,
                    gpu_info, cpu_info,
                    run_id,
                ),
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    def delete_run(self, run_id: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM benchmark_runs WHERE id = ?", (run_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self._close_conn(conn)

    def get_most_recent_run(self, service_name: str) -> Optional[BenchmarkRun]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM benchmark_runs WHERE service_name = ? ORDER BY created_at DESC LIMIT 1",
                (service_name,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_run(row)
        finally:
            self._close_conn(conn)

    def has_running_benchmark(self, service_name: str) -> bool:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM benchmark_runs WHERE service_name = ? AND status IN ('pending', 'running')",
                (service_name,),
            ).fetchone()
            return row[0] > 0
        finally:
            self._close_conn(conn)

    def rename_service(self, old_name: str, new_name: str) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE benchmark_runs SET service_name = ? WHERE service_name = ?",
                (new_name, old_name),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            self._close_conn(conn)

    def recover_stale_runs(self) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE benchmark_runs SET status = 'failed',
                   error_message = 'Benchmark interrupted by server restart',
                   completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                   WHERE status IN ('pending', 'running')"""
            )
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Recovered {count} stale benchmark run(s)")
            return count
        finally:
            self._close_conn(conn)
