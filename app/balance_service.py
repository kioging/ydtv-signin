from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .db import transaction


def record_balance_snapshot(
    database_path: Path,
    account_id: str,
    balance: float,
    captured_at: datetime | None = None,
) -> str:
    moment = captured_at or datetime.now(timezone.utc)
    timestamp = moment.astimezone(timezone.utc).isoformat(timespec="seconds")
    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO balance_snapshots(account_id, captured_at, balance)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id, captured_at) DO UPDATE SET balance=excluded.balance
            """,
            (account_id, timestamp, balance),
        )
    return timestamp
