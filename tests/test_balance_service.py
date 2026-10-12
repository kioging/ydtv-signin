from app.balance_service import record_balance_snapshot
from app.db import migrate
from app.queries import summary


def test_record_balance_snapshot_updates_summary(tmp_path):
    database = tmp_path / "signin.db"
    migrate(database)
    captured_at = record_balance_snapshot(database, "main", 3.5)
    data = summary(database)
    assert data["latest_balances"]["main"]["balance"] == 3.5
    assert data["latest_balances"]["main"]["captured_at"] == captured_at
