from app.db import migrate
from app.queries import account_summaries, runs, summary


def test_summary_empty(tmp_path):
    path = tmp_path / "db.sqlite"
    migrate(path)
    data = summary(path)
    assert data["total_runs"] == 0
    assert data["latest_balances"] == {}
    assert runs(path) == []
    assert account_summaries(path) == []

