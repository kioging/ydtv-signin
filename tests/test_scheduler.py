from pathlib import Path

from app.config import load_config, update_scheduler_settings
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


def test_disabling_scheduler_removes_pending_retries(tmp_path):
    config_path = tmp_path / "config.json"
    from app.config import create_default_config

    create_default_config(config_path)
    config = load_config(config_path, create=False)
    service = SchedulerService(
        config,
        tmp_path / "accounts.json",
        tmp_path / "signin.db",
        StubRunner(),
    )
    service.scheduler.start(paused=True)
    service.scheduler.add_job(lambda: None, "date", id="signin-retry-test-1")
    update_scheduler_settings(
        config,
        enabled=False,
        daily_time=config.scheduler.daily_time,
        jitter_seconds=config.scheduler.jitter_seconds,
        retry_delay_minutes=config.scheduler.retry_delay_minutes,
        max_retries=config.scheduler.max_retries,
        max_concurrency=config.scheduler.max_concurrency,
        keepalive_interval_hours=config.scheduler.keepalive_interval_hours,
    )
    service.reconfigure(load_config(config_path, create=False))
    assert service.scheduler.get_jobs() == []
    service.shutdown()
