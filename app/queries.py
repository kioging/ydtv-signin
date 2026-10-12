from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .db import connect


def _days_ago_iso(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")


def _account_filter(account_ids: set[str] | None, column: str = "account_id") -> tuple[str, list[str]]:
    if account_ids is None:
        return "", []
    if not account_ids:
        return " AND 1 = 0", []
    placeholders = ",".join("?" for _ in account_ids)
    return f" AND {column} IN ({placeholders})", list(account_ids)


def summary(
    database: Path,
    days: int = 30,
    account_ids: set[str] | None = None,
) -> dict[str, Any]:
    since = _days_ago_iso(days)
    account_clause, account_values = _account_filter(account_ids)
    with connect(database, readonly=True) as connection:
        total_runs = connection.execute(
            f"SELECT COUNT(*) AS value FROM runs WHERE started_at >= ?{account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        successful = connection.execute(
            f"SELECT COUNT(*) AS value FROM runs WHERE started_at >= ? AND status = 'success' AND trigger_id NOT LIKE 'keepalive-%'{account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        already = connection.execute(
            f"SELECT COUNT(*) AS value FROM runs WHERE started_at >= ? AND status = 'already_signed' AND trigger_id NOT LIKE 'keepalive-%'{account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        failures = connection.execute(
            f"SELECT COUNT(*) AS value FROM runs WHERE started_at >= ? AND status IN ('failed', 'network_error'){account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        invalid = connection.execute(
            f"SELECT COUNT(*) AS value FROM runs WHERE started_at >= ? AND status = 'token_invalid'{account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        reward = connection.execute(
            f"SELECT COALESCE(SUM(reward), 0) AS value FROM signins WHERE sign_date >= date(?){account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        signed_days = connection.execute(
            f"SELECT COUNT(DISTINCT sign_date) AS value FROM signins WHERE sign_date >= date(?) AND status IN ('success', 'already_signed'){account_clause}",
            (since, *account_values),
        ).fetchone()["value"]
        latest_balance = connection.execute(
            f"""
            SELECT s.account_id, s.balance, s.captured_at
            FROM balance_snapshots s
            JOIN (
                SELECT account_id, MAX(captured_at) AS latest FROM balance_snapshots GROUP BY account_id
            ) latest_rows ON latest_rows.account_id = s.account_id AND latest_rows.latest = s.captured_at
            WHERE 1 = 1{_account_filter(account_ids, 's.account_id')[0]}
            """,
            account_values,
        ).fetchall()
    return {
        "days": days,
        "total_runs": total_runs,
        "successful": successful,
        "already_signed": already,
        "failed": failures,
        "token_invalid": invalid,
        "reward_total": reward,
        "signed_days": signed_days,
        "latest_balances": {
            row["account_id"]: {"balance": row["balance"], "captured_at": row["captured_at"]}
            for row in latest_balance
        },
    }


def account_summaries(database: Path, days: int = 90) -> list[dict[str, Any]]:
    since = _days_ago_iso(days)
    with connect(database, readonly=True) as connection:
        accounts = connection.execute(
            """
            SELECT r.account_id,
                   MAX(r.finished_at) AS last_run,
                   SUM(CASE WHEN r.status = 'success' AND r.trigger_id NOT LIKE 'keepalive-%' THEN 1 ELSE 0 END) AS successful,
                   SUM(CASE WHEN r.status = 'already_signed' AND r.trigger_id NOT LIKE 'keepalive-%' THEN 1 ELSE 0 END) AS already_signed,
                   SUM(CASE WHEN r.status IN ('failed', 'network_error') THEN 1 ELSE 0 END) AS failed,
                   SUM(CASE WHEN r.status = 'token_invalid' THEN 1 ELSE 0 END) AS token_invalid
            FROM runs r
            WHERE r.started_at >= ?
            GROUP BY r.account_id
            ORDER BY r.account_id
            """,
            (since,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in accounts:
            account_id = row["account_id"]
            balance_row = connection.execute(
                "SELECT balance FROM balance_snapshots WHERE account_id = ? ORDER BY captured_at DESC LIMIT 1",
                (account_id,),
            ).fetchone()
            calendar = connection.execute(
                """
                SELECT sign_date, status, reward, milestone_name, milestone_reward
                FROM signins WHERE account_id = ? AND sign_date >= date(?)
                ORDER BY sign_date
                """,
                (account_id, since),
            ).fetchall()
            balances = connection.execute(
                "SELECT captured_at, balance FROM balance_snapshots WHERE account_id = ? AND captured_at >= ? ORDER BY captured_at",
                (account_id, since),
            ).fetchall()
            reward_total = connection.execute(
                """
                SELECT COALESCE(SUM(reward), 0) AS value
                FROM signins
                WHERE account_id = ? AND sign_date >= date(?)
                """,
                (account_id, since),
            ).fetchone()["value"]
            results.append(
                {
                    "account_id": account_id,
                    "last_run": row["last_run"],
                    "successful": row["successful"],
                    "already_signed": row["already_signed"],
                    "signed_count": connection.execute(
                        """
                        SELECT COUNT(DISTINCT sign_date) AS value
                        FROM signins
                        WHERE account_id = ? AND sign_date >= date(?)
                          AND status IN ('success', 'already_signed')
                        """,
                        (account_id, since),
                    ).fetchone()["value"],
                    "failed": row["failed"],
                    "token_invalid": row["token_invalid"],
                    "reward_total": reward_total,
                    "latest_balance": balance_row["balance"] if balance_row else None,
                    "calendar": [dict(item) for item in calendar],
                    "balance_history": [dict(item) for item in balances],
                }
            )
        return results


def runs(database: Path, days: int = 30, limit: int = 500) -> list[dict[str, Any]]:
    since = _days_ago_iso(days)
    with connect(database, readonly=True) as connection:
        rows = connection.execute(
            """
            SELECT trigger_id, account_id, started_at, finished_at, status, message, reward, balance, attempt
            FROM runs WHERE started_at >= ? ORDER BY started_at DESC LIMIT ?
            """,
            (since, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def runtime_logs(
    database: Path,
    *,
    limit: int = 300,
    level: str = "",
    category: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if level:
        clauses.append("level = ?")
        values.append(level.upper())
    if category:
        clauses.append("category = ?")
        values.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(max(1, min(limit, 1000)))
    with connect(database, readonly=True) as connection:
        rows = connection.execute(
            f"""
            SELECT id, created_at, level, category, logger, message
            FROM runtime_logs
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [dict(row) for row in rows]

