from app.db import connect, migrate
from app.queries import account_summaries, runs, summary


def test_summary_empty(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    data = summary(path)
    assert data["total_runs"] == 0
    assert data["latest_balances"] == {}
    assert runs(path) == []
    assert account_summaries(path) == []


def test_summary_filters_deleted_accounts(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    with connect(path) as connection:
        connection.execute(
            "INSERT INTO runs(trigger_id, account_id, started_at, finished_at, status, reward) VALUES (?, ?, ?, ?, ?, ?)",
            ("daily-a", "a", "2026-10-13T00:00:00+00:00", "2026-10-13T00:00:01+00:00", "success", 1),
        )
        connection.execute(
            "INSERT INTO runs(trigger_id, account_id, started_at, finished_at, status, reward) VALUES (?, ?, ?, ?, ?, ?)",
            ("daily-b", "b", "2026-10-13T00:00:00+00:00", "2026-10-13T00:00:01+00:00", "success", 2),
        )
        connection.commit()
    data = summary(path, account_ids={"a"})
    assert data["successful"] == 1

