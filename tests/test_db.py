from app.db import connect, migrate


def test_migrate_and_query(tmp_path):
    path = tmp_path / "signin.db"
    migrate(path)
    with connect(path) as connection:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "signins", "balance_snapshots", "schema_migrations"} <= tables


def test_migrate_creates_account_metadata_table(tmp_path):
    migrate(tmp_path / "signin.db")
    with connect(tmp_path / "signin.db") as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)")}
    assert {"account_id", "label", "avatar_url", "user_id", "token_expires_at", "balance", "updated_at"} <= columns


def test_migrate_advances_existing_schema_version(tmp_path):
    path = tmp_path / "signin.db"
    with connect(path) as connection:
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
        connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")
        connection.commit()
    migrate(path)
    with connect(path) as connection:
        version = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()["version"]
    assert version == 5

