from __future__ import annotations

import sqlite3
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 5


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                reward REAL NOT NULL DEFAULT 0,
                balance REAL,
                attempt INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id, started_at DESC);
            CREATE TABLE IF NOT EXISTS signins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                sign_date TEXT NOT NULL,
                status TEXT NOT NULL,
                reward REAL NOT NULL DEFAULT 0,
                milestone_name TEXT NOT NULL DEFAULT '',
                milestone_reward REAL NOT NULL DEFAULT 0,
                raw_data TEXT NOT NULL DEFAULT '',
                UNIQUE(account_id, sign_date)
            );
            CREATE INDEX IF NOT EXISTS idx_signins_account_date ON signins(account_id, sign_date DESC);
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                balance REAL NOT NULL,
                UNIQUE(account_id, captured_at)
            );
            CREATE INDEX IF NOT EXISTS idx_balance_account_time ON balance_snapshots(account_id, captured_at DESC);
            CREATE TABLE IF NOT EXISTS job_locks (
                name TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                label TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                token_expires_at TEXT NOT NULL DEFAULT '',
                balance REAL,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS runtime_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '系统',
                logger TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runtime_logs_created ON runtime_logs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runtime_logs_category ON runtime_logs(category, created_at DESC);
            """
        )
        current_version = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()["version"]
        if current_version is not None and current_version < 3:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)")}
            if "user_id" not in columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        if current_version is not None and current_version < 4:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)")}
            if "token_expires_at" not in columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN token_expires_at TEXT NOT NULL DEFAULT ''")
        row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        if row["version"] is None:
            connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))
        elif row["version"] > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application version")
        elif row["version"] < SCHEMA_VERSION:
            connection.execute("DELETE FROM schema_migrations")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))


def acquire_job_lock(path: Path, name: str, owner: str, expires_at: str) -> bool:
    with transaction(path) as connection:
        now = datetime.utcnow().isoformat(timespec="seconds")
        row = connection.execute("SELECT owner, expires_at FROM job_locks WHERE name = ?", (name,)).fetchone()
        if row and row["expires_at"] > now:
            return False
        connection.execute(
            "INSERT OR REPLACE INTO job_locks(name, owner, expires_at) VALUES (?, ?, ?)",
            (name, owner, expires_at),
        )
        return True


def release_job_lock(path: Path, name: str, owner: str) -> None:
    with transaction(path) as connection:
        connection.execute("DELETE FROM job_locks WHERE name = ? AND owner = ?", (name, owner))


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

