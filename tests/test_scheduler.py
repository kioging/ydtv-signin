from pathlib import Path

from app.config import load_config
from app.scheduler import SchedulerService


class StubRunner:
    def run(self, *args, **kwargs):
        return []

    def should_retry(self, *args, **kwargs):
        return False

    def run_keepalive(self, *args, **kwargs):
        return []


def test_retry_uses_same_trigger_without_clearing(tmp_path):
    config_path = tmp_path / "config.json"
    from app.config import create_default_config

    create_default_config(config_path)
    service = SchedulerService(
        load_config(config_path, create=False),
        tmp_path / "accounts.json",
        tmp_path / "signin.db",
        StubRunner(),
    )
    calls = []
    service._execute = lambda accounts, trigger_id, attempt: calls.append((trigger_id, attempt))
    service._run_retry(2, "daily-test")
    assert calls == [("daily-test", 2)]
