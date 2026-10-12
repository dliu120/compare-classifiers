"""SQLite store for Runs and their scored rows, plus raw request/response capture as JSONL.

Layout: ``<runs_dir>/bakeoff.sqlite`` (WAL mode) and ``<runs_dir>/raw/<run_id>.jsonl``. Every
insert is idempotent: a row is keyed by (run_id, case_id, question_id, rep). Credential values
given as ``redact`` are replaced by ``***`` in everything persisted, in case a vendor echoes
the token it was sent.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from bakeoff.http import elide_images
from bakeoff.metrics import ResultRow

DB_NAME = "bakeoff.sqlite"
REDACTED = "***"

RESULT_COLUMNS = (
    "run_id", "case_id", "question_id", "rep", "qtype", "n_options", "reference_json",
    "answer_json", "non_answer_cause", "correct", "prob_ref", "prob_pred", "confidence",
    "latency_s", "input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens",
    "cost_usd", "http_status", "attempts", "over_limit", "created_at",
)  # fmt: skip

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    family TEXT NOT NULL,
    config_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    rep INTEGER NOT NULL,
    qtype TEXT NOT NULL,
    n_options INTEGER NOT NULL,
    reference_json TEXT NOT NULL,
    answer_json TEXT NOT NULL,
    non_answer_cause TEXT,
    correct INTEGER NOT NULL,
    prob_ref REAL,
    prob_pred REAL,
    confidence REAL,
    latency_s REAL NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    cached_tokens INTEGER,
    cost_usd REAL,
    http_status INTEGER,
    attempts INTEGER NOT NULL,
    over_limit INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id, question_id, rep)
);
"""

_INSERT_RESULT = (
    f"INSERT OR REPLACE INTO results ({', '.join(RESULT_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in RESULT_COLUMNS)})"
)


class RunRecord(BaseModel):
    run_id: str
    provider_id: str
    family: str
    config: dict[str, Any]
    started_at: str
    finished_at: str | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def has_store(runs_dir: Path) -> bool:
    return (runs_dir / DB_NAME).is_file()


class Store:
    def __init__(self, runs_dir: Path, *, redact: Sequence[str] = ()) -> None:
        self.runs_dir = runs_dir
        self.raw_dir = runs_dir / "raw"
        self._secrets = [secret for secret in redact if secret]
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(runs_dir / DB_NAME)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def begin_run(self, run_id: str, provider_id: str, family: str, config: dict[str, Any]) -> None:
        """Register a Run; a resumed Run keeps its first started_at and reopens finished_at."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs (run_id, provider_id, family, config_json, started_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET "
                "config_json = excluded.config_json, finished_at = NULL",
                (run_id, provider_id, family, json.dumps(config, sort_keys=True), now_iso()),
            )

    def finish_run(self, run_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET finished_at = ? WHERE run_id = ?", (now_iso(), run_id)
            )

    def completed(self, run_id: str) -> set[tuple[str, int]]:
        """(case_id, rep) pairs that have rows. Every Question of a Case is written at once."""
        cursor = self.conn.execute(
            "SELECT DISTINCT case_id, rep FROM results WHERE run_id = ?", (run_id,)
        )
        return {(row["case_id"], row["rep"]) for row in cursor}

    def write_rows(self, rows: list[ResultRow]) -> None:
        with self.conn:
            self.conn.executemany(_INSERT_RESULT, [self._to_db(row) for row in rows])

    def write_raw(self, run_id: str, record: dict[str, Any]) -> None:
        """Append one JSON line of raw capture; images are elided again here as a last defence."""
        path = self.raw_dir / f"{run_id}.jsonl"
        line = json.dumps(elide_images(record), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(self._scrub(line) + "\n")

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def _to_db(self, row: ResultRow) -> tuple[Any, ...]:
        data = row.model_dump()
        data["reference_json"] = json.dumps(data["reference_json"], sort_keys=True)
        data["answer_json"] = self._scrub(json.dumps(data["answer_json"], sort_keys=True))
        data["correct"] = int(data["correct"])
        data["over_limit"] = int(data["over_limit"])
        return tuple(data[column] for column in RESULT_COLUMNS)

    def runs(self) -> list[RunRecord]:
        cursor = self.conn.execute("SELECT * FROM runs ORDER BY family, provider_id")
        return [
            RunRecord(
                run_id=row["run_id"],
                provider_id=row["provider_id"],
                family=row["family"],
                config=json.loads(row["config_json"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in cursor
        ]

    def rows(self, run_id: str) -> list[ResultRow]:
        cursor = self.conn.execute(
            "SELECT * FROM results WHERE run_id = ? ORDER BY case_id, rep, question_id", (run_id,)
        )
        return [_from_db(row) for row in cursor]

    def total_cost_usd(self) -> float:
        """Known spend across every Run, counting each request once."""
        cursor = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM "
            "(SELECT DISTINCT run_id, case_id, rep, cost_usd FROM results)"
        )
        return float(cursor.fetchone()["total"])


def _from_db(row: sqlite3.Row) -> ResultRow:
    data = dict(row)
    data["reference_json"] = json.loads(data["reference_json"])
    data["answer_json"] = json.loads(data["answer_json"])
    return ResultRow.model_validate(data)
