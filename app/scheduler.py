from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from .accounts import Account, load_accounts
from .config import AppConfig
from .db import acquire_job_lock, release_job_lock
from .runner import SigninRunner


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        config: AppConfig,
        accounts_path: Path,
        database_path: Path,
        runner: SigninRunner,
    ) -> None:
        self.config = config
        self.accounts_path = accounts_path
        self.database_path = database_path
        self.runner = runner
        self.scheduler = BackgroundScheduler(timezone=config.site.timezone)

    def start(self) -> None:
        if not self.config.scheduler.enabled:
            logger.info("Scheduler disabled in config")
            return
        self.scheduler.start()
        self._schedule_daily()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reconfigure(self, config: AppConfig) -> None:
        self.config = config
        if not self.scheduler.running:
            self.scheduler.start()
        if not config.scheduler.enabled:
            for job in self.scheduler.get_jobs():
                job.remove()
            logger.info("Scheduler disabled by settings update")
            return
        for job in self.scheduler.get_jobs():
            if job.id.startswith("signin-retry-"):
                continue
            job.remove()
        self._schedule_daily()
        logger.info(
            "Scheduler reconfigured: daily=%s, keepalive=%sh",
            config.scheduler.daily_time,
            config.scheduler.keepalive_interval_hours,
        )

    def _schedule_daily(self) -> None:
        hour, minute = map(int, self.config.scheduler.daily_time.split(":", 1))
        self.scheduler.add_job(
            self._schedule_delayed_daily,
            "cron",
            hour=hour,
            minute=minute,
            second=0,
            id="daily-signin-scheduler",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        if self.config.scheduler.keepalive_interval_hours > 0:
            self.scheduler.add_job(
                self._run_keepalive,
                "interval",
                hours=self.config.scheduler.keepalive_interval_hours,
                id="token-keepalive",
                replace_existing=True,
                misfire_grace_time=1800,
            )

    def _run_keepalive(self) -> None:
        accounts = [account for account in load_accounts(self.accounts_path) if account.enabled]
        if not accounts:
            return
        trigger_id = f"keepalive-{uuid.uuid4().hex[:8]}"
        logger.info("Starting token keepalive %s for %d accounts", trigger_id, len(accounts))
        self.runner.run_keepalive(accounts, trigger_id)
        logger.info("Token keepalive %s completed", trigger_id)

    def _schedule_delayed_daily(self) -> None:
        low, high = self.config.scheduler.jitter_seconds
        delay = random.uniform(low, high)
        self.scheduler.add_job(
            self._run_daily,
            DateTrigger(run_date=datetime.now(self.scheduler.timezone) + timedelta(seconds=delay)),
            id="daily-signin",
            replace_existing=True,
        )

    def _schedule_retry(self, attempt: int, trigger_id: str) -> None:
        job_suffix = trigger_id.replace(":", "-")[-20:]
        self.scheduler.add_job(
            self._run_retry,
            DateTrigger(
                run_date=datetime.now(self.scheduler.timezone)
                + timedelta(minutes=self.config.scheduler.retry_delay_minutes)
            ),
            args=[attempt, trigger_id],
            id=f"signin-retry-{job_suffix}-{attempt}",
            replace_existing=True,
        )

    def _run_daily(self) -> None:
        accounts = load_accounts(self.accounts_path)
        trigger_id = f"daily-{datetime.now(self.scheduler.timezone).date().isoformat()}-{uuid.uuid4().hex[:8]}"
        self._execute(accounts, trigger_id, 0)

    def _run_retry(self, attempt: int, trigger_id: str) -> None:
        accounts = load_accounts(self.accounts_path)
        self._execute(accounts, trigger_id, attempt)

    def _execute(self, accounts: list[Account], trigger_id: str, attempt: int) -> None:
        owner = uuid.uuid4().hex
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds")
        if not acquire_job_lock(self.database_path, f"signin:{trigger_id}", owner, expires_at):
            logger.info("Trigger %s is already being processed", trigger_id)
            return
        try:
            if not accounts:
                logger.warning("No accounts configured")
                return
            logger.info("Starting sign-in trigger %s with %d enabled accounts", trigger_id, sum(a.enabled for a in accounts))
            results = self.runner.run(
                accounts,
                trigger_id,
                attempt,
                max_concurrency=self.config.scheduler.max_concurrency,
            )
            if self.runner.should_retry(results) and attempt < self.config.scheduler.max_retries:
                logger.warning("Scheduling retry %d for trigger %s", attempt + 1, trigger_id)
                self._schedule_retry(attempt + 1, trigger_id)
            else:
                logger.info("Sign-in trigger %s completed", trigger_id)
        finally:
            release_job_lock(self.database_path, f"signin:{trigger_id}", owner)

