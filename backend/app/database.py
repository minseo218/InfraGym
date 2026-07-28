from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def database_path() -> Path:
    value = os.getenv("INFRAGYM_DB_PATH", "./data/infragym.db")
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(database_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_database() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                scenario TEXT NOT NULL,
                stage INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                evidence TEXT NOT NULL DEFAULT '[]',
                score INTEGER NOT NULL DEFAULT 12,
                root_cause TEXT,
                mitigation TEXT,
                prevention TEXT,
                report TEXT
            );

            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                command TEXT NOT NULL,
                output TEXT NOT NULL,
                evidence_type TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS command_session_idx
            ON command_history(session_id, created_at);
            """
        )


def evidence_from_row(row: sqlite3.Row) -> list[str]:
    return list(json.loads(row["evidence"] or "[]"))
