from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect


def _category_for(record: logging.LogRecord) -> str:
    logger_name = record.name
    if logger_name.startswith("httpx"):
        return "ydtv.ai 请求"
    if logger_name.startswith("app.scheduler") or logger_name.startswith("apscheduler"):
        return "调度器"
    if logger_name.startswith("app.auth_flow"):
        return "授权"
    if logger_name.startswith("app.runner"):
        return "签到"
    if logger_name.startswith("app.main"):
        return "Web"
    if logger_name.startswith("uvicorn.access"):
        return "Web访问"
    return "系统"


class DatabaseLogHandler(logging.Handler):
    def __init__(self, database_path: Path, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self.database_path = database_path

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "_ydtv_db_logged", False):
            return
        record._ydtv_db_logged = True
        message = self.format(record)
        if "/static/" in message or "/dashboard/api/auth/status/" in message:
            return
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with connect(self.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO runtime_logs(created_at, level, category, logger, message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        record.levelname,
                        _category_for(record),
                        record.name,
                        message,
                    ),
                )
                connection.commit()
        except (sqlite3.Error, OSError):
            self.handleError(record)


def install_database_logging(database_path: Path, level: int = logging.INFO) -> None:
    if "pytest" in sys.modules:
        return
    formatter = logging.Formatter("%(message)s")
    for logger_name in ("", "uvicorn", "uvicorn.access", "apscheduler", "httpx", "app"):
        target = logging.getLogger(logger_name)
        target.setLevel(min(target.level or level, level))
        if any(isinstance(handler, DatabaseLogHandler) for handler in target.handlers):
            continue
        handler = DatabaseLogHandler(database_path, level=level)
        handler.setFormatter(formatter)
        target.addHandler(handler)


def prune_runtime_logs(database_path: Path, retention_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="seconds")
    with connect(database_path) as connection:
        cursor = connection.execute("DELETE FROM runtime_logs WHERE created_at < ?", (cutoff,))
        connection.commit()
        return cursor.rowcount
