from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from evidex.models import (
    GateResult,
    JobState,
    ModelCallRecord,
    ProjectBrief,
    Stage,
    utc_now,
)
from evidex.state_machine import (
    assert_stage_transition,
    assert_status_transition,
)


class PersistenceError(RuntimeError):
    pass


class IdempotencyConflict(PersistenceError):
    pass


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


class SQLiteStore:
    """Durable local store for jobs, attempts, artifacts, gates, calls, and events."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._lock = threading.RLock()
        self._memory_connection: sqlite3.Connection | None = None
        if self.database_path == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            current_stage TEXT,
            attempt INTEGER NOT NULL,
            task_key TEXT,
            feedback_for_retry TEXT,
            pending_approval TEXT,
            section_queue_json TEXT NOT NULL,
            section_cursor INTEGER NOT NULL,
            review_cycle INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            input_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id),
            occurred_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            stage TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, event_id);
        CREATE TABLE IF NOT EXISTS attempts (
            job_id TEXT NOT NULL REFERENCES jobs(job_id),
            stage TEXT NOT NULL,
            task_key TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            status TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT,
            error_text TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            PRIMARY KEY(job_id, stage, task_key, attempt)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id),
            stage TEXT NOT NULL,
            task_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, stage, task_key, version)
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id, stage, task_key, version);
        CREATE TABLE IF NOT EXISTS gate_results (
            gate_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id),
            stage TEXT NOT NULL,
            task_key TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, stage, task_key, attempt)
        );
        CREATE TABLE IF NOT EXISTS model_calls (
            model_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id),
            idempotency_key TEXT NOT NULL UNIQUE,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
        with self._lock:
            connection = self._connect()
            try:
                connection.executescript(schema)
                connection.commit()
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def create_job(self, brief: ProjectBrief, job_id: str) -> JobState:
        state = JobState(job_id=job_id)
        now = _iso(state.created_at)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO jobs (
                        job_id, status, current_stage, attempt, task_key, feedback_for_retry,
                        pending_approval, section_queue_json, section_cursor, review_cycle,
                        data_json, input_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_id,
                        state.status.value,
                        state.current_stage.value if state.current_stage else None,
                        state.attempt,
                        state.task_key,
                        state.feedback_for_retry,
                        None,
                        _json(state.section_queue),
                        state.section_cursor,
                        state.review_cycle,
                        _json(state.data),
                        _json(brief),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO events(job_id, occurred_at, event_type, stage, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        job_id,
                        now,
                        "job_created",
                        Stage.INTAKE.value,
                        _json(
                            {"brief": brief.model_dump(mode="json"), "status": state.status.value}
                        ),
                    ),
                )
                connection.commit()
                return state
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def get_job(self, job_id: str) -> JobState:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"Job not found: {job_id}")
                return self._row_to_state(row)
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def get_input(self, job_id: str) -> ProjectBrief:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT input_json FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"Job not found: {job_id}")
                return ProjectBrief.model_validate(_decode(row["input_json"]))
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> JobState:
        return JobState.model_validate(
            {
                "job_id": row["job_id"],
                "status": row["status"],
                "current_stage": row["current_stage"],
                "attempt": row["attempt"],
                "task_key": row["task_key"],
                "feedback_for_retry": row["feedback_for_retry"],
                "pending_approval": row["pending_approval"],
                "section_queue": _decode(row["section_queue_json"], []),
                "section_cursor": row["section_cursor"],
                "review_cycle": row["review_cycle"],
                "data": _decode(row["data_json"], {}),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def transition_job(
        self,
        job_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        review_routed: bool = False,
        **changes: Any,
    ) -> JobState:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"Job not found: {job_id}")
                old_state = self._row_to_state(row)
                old_data = old_state.model_dump(mode="json")
                state_data = dict(old_data)
                state_data.update(changes)
                state_data["updated_at"] = utc_now().isoformat()
                new_state = JobState.model_validate(state_data)
                assert_status_transition(old_state.status, new_state.status)
                assert_stage_transition(
                    old_state.current_stage,
                    new_state.current_stage,
                    review_routed=review_routed,
                )
                connection.execute(
                    """UPDATE jobs SET status=?, current_stage=?, attempt=?, task_key=?,
                    feedback_for_retry=?, pending_approval=?, section_queue_json=?, section_cursor=?,
                    review_cycle=?, data_json=?, updated_at=? WHERE job_id=?""",
                    (
                        new_state.status.value,
                        new_state.current_stage.value if new_state.current_stage else None,
                        new_state.attempt,
                        new_state.task_key,
                        new_state.feedback_for_retry,
                        new_state.pending_approval.value if new_state.pending_approval else None,
                        _json(new_state.section_queue),
                        new_state.section_cursor,
                        new_state.review_cycle,
                        _json(new_state.data),
                        _iso(new_state.updated_at),
                        job_id,
                    ),
                )
                event_stage = new_state.current_stage or old_state.current_stage
                event_payload = {
                    "from_status": old_state.status.value,
                    "to_status": new_state.status.value,
                    "from_stage": old_state.current_stage.value
                    if old_state.current_stage
                    else None,
                    "to_stage": new_state.current_stage.value if new_state.current_stage else None,
                    **(payload or {}),
                }
                connection.execute(
                    "INSERT INTO events(job_id, occurred_at, event_type, stage, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        job_id,
                        _iso(new_state.updated_at),
                        event_type,
                        event_stage.value if event_stage else None,
                        _json(event_payload),
                    ),
                )
                connection.commit()
                return new_state
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def start_attempt(
        self,
        job_id: str,
        stage: Stage,
        task_key: str,
        attempt: int,
        input_payload: dict[str, Any],
    ) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """INSERT OR IGNORE INTO attempts(
                        job_id, stage, task_key, attempt, status, input_json, started_at
                    ) VALUES (?, ?, ?, ?, 'running', ?, ?)""",
                    (job_id, stage.value, task_key, attempt, _json(input_payload), _iso()),
                )
                connection.commit()
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def get_attempt(
        self, job_id: str, stage: Stage, task_key: str, attempt: int
    ) -> dict[str, Any] | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM attempts WHERE job_id=? AND stage=? AND task_key=? AND attempt=?",
                    (job_id, stage.value, task_key, attempt),
                ).fetchone()
                if row is None:
                    return None
                return {
                    "job_id": row["job_id"],
                    "stage": row["stage"],
                    "task_key": row["task_key"],
                    "attempt": row["attempt"],
                    "status": row["status"],
                    "input": _decode(row["input_json"], {}),
                    "output": _decode(row["output_json"]),
                    "error": row["error_text"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                }
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def finish_attempt(
        self,
        job_id: str,
        stage: Stage,
        task_key: str,
        attempt: int,
        *,
        status: str,
        output: Any,
        error: str | None = None,
    ) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """UPDATE attempts SET status=?, output_json=?, error_text=?, finished_at=?
                    WHERE job_id=? AND stage=? AND task_key=? AND attempt=?""",
                    (status, _json(output), error, _iso(), job_id, stage.value, task_key, attempt),
                )
                connection.commit()
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def save_artifact(
        self,
        job_id: str,
        stage: Stage,
        task_key: str,
        version: int,
        content: Any,
    ) -> None:
        content_json = _json(content)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """INSERT OR IGNORE INTO artifacts(job_id, stage, task_key, version, content_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (job_id, stage.value, task_key, version, content_json, _iso()),
                )
                row = connection.execute(
                    "SELECT content_json FROM artifacts WHERE job_id=? AND stage=? AND task_key=? AND version=?",
                    (job_id, stage.value, task_key, version),
                ).fetchone()
                if row["content_json"] != content_json:
                    raise IdempotencyConflict(
                        f"Attempt {job_id}/{stage.value}/{task_key}/{version} produced a different artifact on replay"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def get_artifact(
        self, job_id: str, stage: Stage, task_key: str = "default", version: int | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            connection = self._connect()
            try:
                if version is None:
                    row = connection.execute(
                        """SELECT content_json FROM artifacts WHERE job_id=? AND stage=? AND task_key=?
                        ORDER BY version DESC LIMIT 1""",
                        (job_id, stage.value, task_key),
                    ).fetchone()
                else:
                    row = connection.execute(
                        "SELECT content_json FROM artifacts WHERE job_id=? AND stage=? AND task_key=? AND version=?",
                        (job_id, stage.value, task_key, version),
                    ).fetchone()
                return _decode(row["content_json"]) if row else None
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM artifacts WHERE job_id=? ORDER BY artifact_id", (job_id,)
                ).fetchall()
                return [
                    {
                        "stage": row["stage"],
                        "task_key": row["task_key"],
                        "version": row["version"],
                        "content": _decode(row["content_json"]),
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def save_gate_result(
        self, job_id: str, stage: Stage, task_key: str, attempt: int, result: GateResult
    ) -> None:
        result_json = _json(result)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """INSERT OR IGNORE INTO gate_results(job_id, stage, task_key, attempt, result_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (job_id, stage.value, task_key, attempt, result_json, _iso()),
                )
                row = connection.execute(
                    "SELECT result_json FROM gate_results WHERE job_id=? AND stage=? AND task_key=? AND attempt=?",
                    (job_id, stage.value, task_key, attempt),
                ).fetchone()
                if row["result_json"] != result_json:
                    raise IdempotencyConflict(
                        "A gate result for this stage attempt already differs"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def get_gate_result(
        self, job_id: str, stage: Stage, task_key: str, attempt: int
    ) -> GateResult | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT result_json FROM gate_results WHERE job_id=? AND stage=? AND task_key=? AND attempt=?",
                    (job_id, stage.value, task_key, attempt),
                ).fetchone()
                return GateResult.model_validate(_decode(row["result_json"])) if row else None
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def save_model_call(self, record: ModelCallRecord) -> None:
        record_json = _json(record)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    "INSERT OR IGNORE INTO model_calls(job_id, idempotency_key, record_json, created_at) VALUES (?, ?, ?, ?)",
                    (record.job_id, record.idempotency_key, record_json, _iso(record.created_at)),
                )
                row = connection.execute(
                    "SELECT record_json FROM model_calls WHERE idempotency_key=?",
                    (record.idempotency_key,),
                ).fetchone()
                if row["record_json"] != record_json:
                    raise IdempotencyConflict(
                        "Model-call idempotency key was reused with different metadata"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def list_model_calls(self, job_id: str) -> list[ModelCallRecord]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT record_json FROM model_calls WHERE job_id=? ORDER BY model_call_id",
                    (job_id,),
                ).fetchall()
                return [ModelCallRecord.model_validate(_decode(row["record_json"])) for row in rows]
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def list_attempts(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM attempts WHERE job_id=? ORDER BY started_at, stage, task_key, attempt",
                    (job_id,),
                ).fetchall()
                return [
                    {
                        "stage": row["stage"],
                        "task_key": row["task_key"],
                        "attempt": row["attempt"],
                        "status": row["status"],
                        "input": _decode(row["input_json"], {}),
                        "output": _decode(row["output_json"]),
                        "error": row["error_text"],
                        "started_at": row["started_at"],
                        "finished_at": row["finished_at"],
                    }
                    for row in rows
                ]
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def append_event(
        self, job_id: str, event_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        state = self.get_job(job_id)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    "INSERT INTO events(job_id, occurred_at, event_type, stage, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        job_id,
                        _iso(),
                        event_type,
                        state.current_stage.value if state.current_stage else None,
                        _json(payload or {}),
                    ),
                )
                connection.commit()
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def list_events(self, job_id: str, after_event_id: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM events WHERE job_id=? AND event_id>? ORDER BY event_id",
                    (job_id, after_event_id),
                ).fetchall()
                return [
                    {
                        "event_id": row["event_id"],
                        "occurred_at": row["occurred_at"],
                        "event_type": row["event_type"],
                        "stage": row["stage"],
                        "payload": _decode(row["payload_json"], {}),
                    }
                    for row in rows
                ]
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def close(self) -> None:
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None
