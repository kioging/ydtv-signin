from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

from .account_sync import sync_account
from .ydtv import YdtvClient


logger = logging.getLogger(__name__)


@dataclass
class AuthFlowStatus:
    state: str
    message: str = ""
    account_id: str = ""


class AuthFlowManager:
    def __init__(self, accounts_path: Path, profile_path: Path, client: YdtvClient) -> None:
        self.accounts_path = accounts_path
        self.profile_path = profile_path
        self.client = client
        self.database_path = accounts_path.parent / "data" / "signin.db"
        self._lock = threading.Lock()
        self._statuses: dict[str, AuthFlowStatus] = {}
        self._threads: dict[str, threading.Thread] = {}

    def start(self, account_id: str, label: str, home_url: str) -> str:
        with self._lock:
            for existing_id, existing in self._statuses.items():
                if existing.account_id == account_id and existing.state in {"waiting", "verifying"}:
                    return existing_id
        flow_id = uuid.uuid4().hex
        logger.info("Authorization started for account_id=%s label=%s", account_id, label)
        status = AuthFlowStatus("waiting", "浏览器已打开，请在其中完成登录", account_id)
        with self._lock:
            self._statuses[flow_id] = status
        thread = threading.Thread(
            target=self._run,
            args=(flow_id, account_id, label, home_url),
            daemon=True,
            name=f"ydtv-auth-{flow_id}",
        )
        with self._lock:
            self._threads[flow_id] = thread
        thread.start()
        return flow_id

    def status(self, flow_id: str) -> AuthFlowStatus | None:
        with self._lock:
            status = self._statuses.get(flow_id)
            return AuthFlowStatus(**vars(status)) if status else None

    def _set_status(self, flow_id: str, **kwargs) -> None:
        with self._lock:
            status = self._statuses[flow_id]
            for key, value in kwargs.items():
                setattr(status, key, value)

    def _profile_for(self, account_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", account_id) or "account"
        return self.profile_path / safe_id

    def _run(self, flow_id: str, account_id: str, label: str, home_url: str) -> None:
        profile_path = self._profile_for(account_id)
        profile_path.mkdir(parents=True, exist_ok=True)
        context = None
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(profile_path),
                    headless=False,
                    viewport={"width": 1280, "height": 860},
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
                deadline = time.time() + 600
                rejected_token = ""
                while time.time() < deadline:
                    try:
                        token = page.evaluate("localStorage.getItem('token') || ''")
                    except Exception as error:
                        if "closed" in str(error).lower():
                            self._set_status(flow_id, state="failed", message="授权窗口已关闭")
                            return
                        raise
                    if token and token != rejected_token:
                        self._set_status(flow_id, state="verifying", message="正在验证登录状态")
                        logger.info(
                            "Authorization token captured for account_id=%s profile=%s; verifying",
                            account_id,
                            profile_path.name,
                        )
                        response = self.client.verify_token(token)
                        if response.status_code == 200 and response.payload.get("code") in (None, 200):
                            sync_result = sync_account(
                                self.accounts_path,
                                self.database_path,
                                account_id,
                                self.client,
                                token,
                                verification_payload=response.payload,
                            )
                            if sync_result.created:
                                message = f"新账号 {sync_result.label} 已添加"
                            else:
                                message = f"账号 {sync_result.label} 已存在，已覆盖原登录 Token"
                            logger.info(
                                "Authorization completed for account_id=%s label=%s created=%s",
                                sync_result.account_id,
                                sync_result.label,
                                sync_result.created,
                            )
                            self._set_status(flow_id, state="success", message=message)
                            return

                        rejected_token = token
                        message = str(
                            response.payload.get("msg")
                            or response.payload.get("message")
                            or f"HTTP {response.status_code}"
                        )
                        logger.warning(
                            "Authorization token rejected for account_id=%s: %s; waiting for re-login",
                            account_id,
                            message,
                        )
                        try:
                            page.evaluate("localStorage.removeItem('token')")
                        except Exception:
                            pass
                        self._set_status(
                            flow_id,
                            state="waiting",
                            message="原登录已失效，请在浏览器中重新完成登录",
                        )
                        page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(1)

                logger.warning("Authorization timed out for account_id=%s", account_id)
                self._set_status(flow_id, state="timeout", message="登录等待超时")
        except Exception as error:
            logger.exception("Authorization flow failed")
            raw_message = str(error)
            if any(
                marker in raw_message
                for marker in ("Missing X server", "$DISPLAY", "headed browser", "browser was not found")
            ):
                raw_message = (
                    "当前服务无法打开图形浏览器。请在桌面终端运行："
                    "python -m app.cli account authorize"
                )
            self._set_status(flow_id, state="failed", message=raw_message)
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
