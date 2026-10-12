from __future__ import annotations

import json
import logging
import random
import sqlite3
import uuid
import httpx
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .accounts import Account
from .account_sync import AccountNotFoundError, sync_account
from .balance_service import record_balance_snapshot
from .db import is_account_deleted, transaction
from .ydtv import ApiResponse, YdtvClient


logger = logging.getLogger(__name__)


@dataclass
class AccountResult:
    account_id: str
    status: str
    message: str = ""
    reward: float = 0.0
    balance: float | None = None


def _parse_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_balance(payload: dict) -> float | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("余额", "剩余额度", "balance", "credits"):
        if key in data:
            return _parse_float(data[key])
    return None


class SigninRunner:
    def __init__(
        self,
        database: Path,
        client: YdtvClient,
        timezone_name: str = "Asia/Shanghai",
        accounts_path: Path | None = None,
    ) -> None:
        self.database = database
        self.client = client
        self.accounts_path = accounts_path
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            self.timezone = timezone.utc

    def _now(self) -> datetime:
        return datetime.now(self.timezone)

    def _utc_timestamp(self, value: datetime | None = None) -> str:
        moment = value or self._now()
        return moment.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _record_run(
        self,
        trigger_id: str,
        account: Account,
        started_at: str,
        result: AccountResult,
        attempt: int,
    ) -> None:
        with transaction(self.database) as connection:
            connection.execute(
                """
                INSERT INTO runs(trigger_id, account_id, started_at, finished_at, status, message, reward, balance, attempt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trigger_id,
                    account.id,
                    started_at,
                    self._utc_timestamp(),
                    result.status,
                    result.message,
                    result.reward,
                    result.balance,
                    attempt,
                ),
            )

    def _record_signin(
        self,
        account: Account,
        sign_date: date,
        result: AccountResult,
        raw_data: dict,
    ) -> None:
        milestone = raw_data.get("data", {}) if isinstance(raw_data.get("data"), dict) else {}
        milestone_name = str(milestone.get("里程碑名称") or "")
        milestone_reward = _parse_float(milestone.get("里程碑金额")) or 0.0
        with transaction(self.database) as connection:
            connection.execute(
                """
                INSERT INTO signins(account_id, sign_date, status, reward, milestone_name, milestone_reward, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, sign_date) DO UPDATE SET
                  status=excluded.status,
                  reward=CASE WHEN excluded.reward > 0 THEN excluded.reward ELSE signins.reward END,
                  milestone_name=CASE WHEN excluded.milestone_name != '' THEN excluded.milestone_name ELSE signins.milestone_name END,
                  milestone_reward=CASE WHEN excluded.milestone_reward > 0 THEN excluded.milestone_reward ELSE signins.milestone_reward END,
                  raw_data=excluded.raw_data
                """,
                (
                    account.id,
                    sign_date.isoformat(),
                    result.status,
                    result.reward,
                    milestone_name,
                    milestone_reward,
                    json.dumps(raw_data, ensure_ascii=False),
                ),
            )

    def _record_balance(self, account: Account, balance: float) -> None:
        record_balance_snapshot(self.database, account.id, balance)

    def _is_auth_failure(self, response: ApiResponse) -> bool:
        return response.status_code == 401 or response.payload.get("code") == 401

    def _sync_profile(
        self,
        account: Account,
        token: str,
        verification_payload: dict | None = None,
    ):
        if not self.accounts_path:
            return None
        try:
            return sync_account(
                self.accounts_path,
                self.database,
                account.id,
                self.client,
                token,
                verification_payload=verification_payload,
                allow_create=False,
            )
        except AccountNotFoundError:
            raise
        except Exception:
            logger.warning("Could not update profile for %s", account.id, exc_info=True)
            return None

    def _query_balance(self, account: Account) -> float | None:
        response = self.client.get_balance(account.token, account.space)
        if self._is_auth_failure(response):
            raise RuntimeError("Token invalid")
        if response.status_code != 200 or response.payload.get("code") not in (None, 200):
            logger.warning("Balance query failed for %s: %s", account.id, response.payload.get("msg"))
            return None
        balance = _extract_balance(response.payload)
        if balance is not None:
            self._record_balance(account, balance)
        return balance

    def _reward_from(self, payload: dict) -> float:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for key in ("总奖励金额", "奖励金额", "今日奖励金额", "签到奖励", "奖励"):
            if key in data:
                reward = _parse_float(data[key])
                if reward is not None:
                    return reward
        return 0.0

    def _today_reward_from_status(self, payload: dict, sign_date: date) -> float:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for item in data.get("本月签到") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("日期") or "")[:10] != sign_date.isoformat():
                continue
            keys = ("奖励金额", "追加奖励金额", "里程碑金额", "里程碑追加金额")
            return sum(_parse_float(item.get(key)) or 0.0 for key in keys)
        return 0.0

    def _try_query_balance(self, account: Account) -> float | None:
        try:
            return self._query_balance(account)
        except Exception:
            logger.warning("Balance query failed for %s; sign-in result is preserved", account.id, exc_info=True)
            return None

    def run_account(self, account: Account, trigger_id: str, attempt: int = 0) -> AccountResult:
        started_at = self._utc_timestamp()
        try:
            if is_account_deleted(self.database, account.id):
                result = AccountResult(account.id, "deleted", "Account was deleted")
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result
            verification = self.client.verify_token(account.token, account.space)
            if self._is_auth_failure(verification):
                result = AccountResult(account.id, "token_invalid", "Token is invalid; sign in again and update accounts.json")
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result
            if verification.status_code != 200 or verification.payload.get("code") not in (None, 200):
                result = AccountResult(
                    account.id,
                    "failed",
                    str(verification.payload.get("msg") or "Token verification failed"),
                )
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result

            try:
                sync_result = self._sync_profile(account, account.token, verification.payload)
            except AccountNotFoundError:
                result = AccountResult(account.id, "deleted", "Account was deleted during execution")
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result
            if sync_result is not None:
                account = replace(
                    account,
                    label=sync_result.label,
                    token=sync_result.token,
                    avatar_url=sync_result.avatar_url,
                    user_id=sync_result.user_id,
                    token_expires_at=sync_result.token_expires_at,
                )

            status_response = self.client.get_signin_status(account.token, account.space)
            if self._is_auth_failure(status_response):
                result = AccountResult(account.id, "token_invalid", "Token became invalid while reading sign-in status")
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result
            if status_response.status_code != 200 or status_response.payload.get("code") != 200:
                result = AccountResult(account.id, "failed", str(status_response.payload.get("msg") or "Sign-in status query failed"))
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result

            status_data = status_response.payload.get("data") or {}
            sign_date = self._now().date()
            if status_data.get("今日已签"):
                result = AccountResult(account.id, "already_signed", "Already signed today")
                result.reward = self._today_reward_from_status(status_response.payload, sign_date)
                self._record_signin(account, sign_date, result, status_response.payload)
                result.balance = self._try_query_balance(account)
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result

            try:
                sign_response = self.client.sign(account.token, account.space)
            except httpx.TransportError:
                check_again = self.client.get_signin_status(account.token, account.space)
                if check_again.status_code == 200 and isinstance(check_again.payload.get("data"), dict) and check_again.payload["data"].get("今日已签"):
                    raw = check_again.payload
                    result = AccountResult(account.id, "success", "Sign-in confirmed after network uncertainty")
                    result.reward = self._reward_from(raw)
                    self._record_signin(account, sign_date, result, raw)
                    result.balance = self._try_query_balance(account)
                    self._record_run(trigger_id, account, started_at, result, attempt)
                    return result
                raise
            if self._is_auth_failure(sign_response):
                result = AccountResult(account.id, "token_invalid", "Token became invalid while signing in")
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result
            if sign_response.status_code != 200 or sign_response.payload.get("code") != 200:
                # A timeout may have signed successfully, so re-query before retrying.
                check_again = self.client.get_signin_status(account.token, account.space)
                if check_again.status_code == 200 and isinstance(check_again.payload.get("data"), dict) and check_again.payload["data"].get("今日已签"):
                    result = AccountResult(account.id, "success", "Sign-in confirmed after network uncertainty")
                    raw = check_again.payload
                    result.reward = self._reward_from(raw)
                    self._record_signin(account, sign_date, result, raw)
                    result.balance = self._try_query_balance(account)
                    self._record_run(trigger_id, account, started_at, result, attempt)
                    return result
                result = AccountResult(account.id, "failed", str(sign_response.payload.get("msg") or "Sign-in failed"))
                self._record_run(trigger_id, account, started_at, result, attempt)
                return result

            raw = sign_response.payload
            reward = self._reward_from(raw)
            result = AccountResult(account.id, "success", str(raw.get("msg") or "Signed in successfully"))
            result.reward = reward
            self._record_signin(account, sign_date, result, raw)
            result.balance = self._try_query_balance(account)
            self._record_run(trigger_id, account, started_at, result, attempt)
            return result
        except Exception as error:
            logger.exception("Account %s failed", account.id)
            result = AccountResult(account.id, "network_error", str(error))
            try:
                self._record_run(trigger_id, account, started_at, result, attempt)
            except sqlite3.Error:
                logger.exception("Could not persist run result for %s", account.id)
            return result

    def run(
        self,
        accounts: list[Account],
        trigger_id: str | None = None,
        attempt: int = 0,
        max_concurrency: int = 1,
    ) -> list[AccountResult]:
        trigger = trigger_id or f"run-{uuid.uuid4()}"
        enabled_accounts = [account for account in accounts if account.enabled]
        if max_concurrency <= 1 or len(enabled_accounts) <= 1:
            return [self.run_account(account, trigger, attempt) for account in enabled_accounts]
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            return list(executor.map(lambda account: self.run_account(account, trigger, attempt), enabled_accounts))

    def should_retry(self, results: list[AccountResult]) -> bool:
        return any(result.status in {"failed", "network_error"} for result in results)

    def random_jitter(self, bounds: tuple[int, int]) -> float:
        return random.uniform(*bounds)

    def next_retry_delay(self, retry_delay_minutes: int) -> timedelta:
        return timedelta(minutes=retry_delay_minutes)

    def run_keepalive(self, accounts: list[Account], trigger_id: str) -> list[AccountResult]:
        results: list[AccountResult] = []
        for account in accounts:
            started_at = self._utc_timestamp()
            try:
                if is_account_deleted(self.database, account.id):
                    result = AccountResult(account.id, "deleted", "Account was deleted")
                    self._record_run(trigger_id, account, started_at, result, attempt=0)
                    results.append(result)
                    continue
                response = self.client.verify_token(account.token, account.space)
                if self._is_auth_failure(response):
                    result = AccountResult(account.id, "token_invalid", "Token is invalid; authorize this account again")
                elif response.status_code == 200 and response.payload.get("code") in (None, 200):
                    try:
                        self._sync_profile(account, account.token, response.payload)
                    except AccountNotFoundError:
                        result = AccountResult(account.id, "deleted", "Account was deleted during keepalive")
                    else:
                        result = AccountResult(account.id, "success", "Token valid")
                else:
                    result = AccountResult(account.id, "failed", str(response.payload.get("msg") or "Token verification failed"))
            except Exception as error:
                logger.exception("Keepalive failed for %s", account.id)
                result = AccountResult(account.id, "network_error", str(error))
            self._record_run(trigger_id, account, started_at, result, attempt=0)
            results.append(result)
        return results

