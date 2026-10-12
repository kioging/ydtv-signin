import logging

from app.db import connect, migrate
from app.log_store import DatabaseLogHandler
from app.queries import runtime_logs


def test_database_log_handler_persists_log(tmp_path):
    database = tmp_path / "signin.db"
    migrate(database)
    logger = logging.getLogger("test.runtime")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = DatabaseLogHandler(database)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]

    logger.info("daily scheduler executed")

    rows = runtime_logs(database)
    assert rows[0]["message"] == "daily scheduler executed"
    assert rows[0]["level"] == "INFO"


def test_runtime_logs_filter(tmp_path):
    database = tmp_path / "signin.db"
    migrate(database)
    with connect(database) as connection:
        connection.execute(
            "INSERT INTO runtime_logs(created_at, level, category, logger, message) VALUES (?, ?, ?, ?, ?)",
            ("2026-10-12T10:00:00+00:00", "ERROR", "调度器", "app.scheduler", "failed"),
        )
        connection.execute(
            "INSERT INTO runtime_logs(created_at, level, category, logger, message) VALUES (?, ?, ?, ?, ?)",
            ("2026-10-12T10:01:00+00:00", "INFO", "Web", "app.main", "ok"),
        )
        connection.commit()
    rows = runtime_logs(database, level="ERROR", category="调度器")
    assert len(rows) == 1
    assert rows[0]["message"] == "failed"


def test_login_actions_are_categorized_as_authorization(tmp_path):
    database = tmp_path / "signin.db"
    migrate(database)
    handler = DatabaseLogHandler(database)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("app.main.test.authorization")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = [handler]

    logger.info("User action: account login, type=password")
    logger.info("User action: complete WeChat account login")
    logger.info("User action: refresh balance")

    rows = runtime_logs(database, category="授权")
    assert len(rows) == 2
