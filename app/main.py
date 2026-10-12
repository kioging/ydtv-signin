from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import (
    COOKIE_NAME,
    LoginRateLimiter,
    create_session_cookie,
    csrf_token,
    is_authenticated,
    validate_csrf_token,
    verify_password,
)
from .config import hash_password, load_config, set_web_password, update_scheduler_settings
from .accounts import load_accounts
from .auth_flow import AuthFlowManager
from .account_sync import sync_account
from .balance_service import record_balance_snapshot
from .db import migrate
from .log_store import install_database_logging, prune_runtime_logs
from .queries import account_summaries, runs, runtime_logs, summary
from .runner import SigninRunner
from .scheduler import SchedulerService
from .ydtv import YdtvClient


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = (
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
DATA_DEFAULT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
DATA_ROOT = Path(os.environ.get("YDTV_DATA_DIR", str(DATA_DEFAULT))).resolve()
CONFIG_PATH = DATA_ROOT / "config.json"
ACCOUNTS_PATH = DATA_ROOT / "accounts.json"
AUTH_PROFILE_PATH = DATA_ROOT / ".auth-profile"
DATABASE_PATH = DATA_ROOT / "data" / "signin.db"

config = load_config(CONFIG_PATH)
migrate(DATABASE_PATH)
prune_runtime_logs(DATABASE_PATH, config.logging.retention_days)
install_database_logging(DATABASE_PATH, getattr(logging, config.logging.level, logging.INFO))

app = FastAPI(title="ydtv.ai Sign-in Panel", docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
rate_limiter = LoginRateLimiter()
runner = SigninRunner(
    DATABASE_PATH,
    YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language),
    config.site.timezone,
    ACCOUNTS_PATH,
)
scheduler_service = SchedulerService(config, ACCOUNTS_PATH, DATABASE_PATH, runner)
scheduler_service.start()
logger.info("Application service started; scheduler and web panel are ready")
auth_flow_manager = AuthFlowManager(
    ACCOUNTS_PATH,
    AUTH_PROFILE_PATH,
    YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language),
)


def local_time_text(value: str | None) -> str:
    if not value:
        return "暂无记录"
    try:
        zone = ZoneInfo(config.site.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S")


def token_expiry_text(value: str) -> str:
    if not value:
        return "未知"
    try:
        zone = ZoneInfo(config.site.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    try:
        expires = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=zone)
    except ValueError:
        return value
    remaining = expires - datetime.now(zone)
    if remaining.total_seconds() <= 0:
        return f"{value}（已过期）"
    return f"{value}（剩余 {remaining.days} 天 {remaining.seconds // 3600} 小时）"


class AuthStartRequest(BaseModel):
    account_id: str = Field(default="", min_length=0, max_length=64)
    label: str = Field(default="", min_length=0, max_length=64)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def require_auth(request: Request) -> None:
    if not await is_authenticated(request, config.web.session_secret):
        raise HTTPException(status_code=401, detail="Authentication required")


def require_csrf(token: str | None) -> None:
    if not validate_csrf_token(config.web.session_secret, token or ""):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login")
async def login_page(request: Request, message: str = ""):
    if await is_authenticated(request, config.web.session_secret):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None, "message": message})


@app.post("/login")
async def login(request: Request, response: Response, password: Annotated[str, Form()]):
    client_ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_blocked(client_ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Too many failed attempts. Try again later.", "message": ""},
            status_code=429,
        )
    if not config.web.password_hash or not verify_password(config.web.password_hash, password):
        rate_limiter.record_failure(client_ip)
        return templates.TemplateResponse(request, "login.html", {"error": "Incorrect password.", "message": ""}, status_code=401)
    rate_limiter.reset(client_ip)
    signed = create_session_cookie(config.web.session_secret, config.web.session_ttl_hours)
    redirect = RedirectResponse("/", status_code=303)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    secure_cookie = forwarded_proto == "https" or request.url.scheme == "https"
    redirect.set_cookie(
        COOKIE_NAME,
        signed,
        max_age=config.web.session_ttl_hours * 3600,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )
    return redirect


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/")
async def dashboard(request: Request, _: None = Depends(require_auth)):
    data = summary(DATABASE_PATH, 30)
    names = {account.id: account.label for account in load_accounts(ACCOUNTS_PATH)}
    data["latest_balances_display"] = []
    for account_id, balance_data in data["latest_balances"].items():
        data["latest_balances_display"].append(
            {
                "account_id": account_id,
                "name": names.get(account_id, account_id),
                "balance": balance_data["balance"],
                "updated_at": local_time_text(balance_data.get("captured_at")),
            }
        )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"summary": data, "csrf_token": csrf_token(config.web.session_secret)},
    )


@app.get("/history")
async def history(request: Request, days: int = 30, _: None = Depends(require_auth)):
    data = runs(DATABASE_PATH, days)
    names = {account.id: account.label for account in load_accounts(ACCOUNTS_PATH)}
    for item in data:
        item["account_name"] = names.get(item["account_id"], item["account_id"])
        item["started_at"] = local_time_text(item["started_at"])
    return templates.TemplateResponse(
        request,
        "history.html",
        {"runs": data, "days": days, "csrf_token": csrf_token(config.web.session_secret)},
    )


@app.get("/logs")
async def logs_page(
    request: Request,
    limit: int = 300,
    level: str = "",
    category: str = "",
    _: None = Depends(require_auth),
):
    data = runtime_logs(DATABASE_PATH, limit=limit, level=level, category=category)
    for item in data:
        item["created_at"] = local_time_text(item["created_at"])
    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "logs": data,
            "limit": limit,
            "selected_level": level,
            "selected_category": category,
            "categories": ["系统", "调度器", "签到", "授权", "ydtv.ai 请求", "Web", "Web访问"],
            "csrf_token": csrf_token(config.web.session_secret),
        },
    )


def settings_response(
    request: Request,
    *,
    message: str = "",
    error: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "current": config,
            "message": message,
            "error": error,
            "csrf_token": csrf_token(config.web.session_secret),
        },
        status_code=status_code,
    )


@app.get("/settings")
async def settings_page(
    request: Request,
    message: str = "",
    error: str = "",
    _: None = Depends(require_auth),
):
    return settings_response(request, message=message, error=error)


@app.post("/settings/password")
async def save_web_password(
    request: Request,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_form_token: Annotated[str, Form(alias="csrf_token")],
    _: None = Depends(require_auth),
):
    global config
    require_csrf(csrf_form_token)
    if not verify_password(config.web.password_hash, current_password):
        return settings_response(request, error="当前 Web 密码不正确", status_code=400)
    if len(new_password) < 8:
        return settings_response(request, error="新密码至少需要 8 个字符", status_code=400)
    if new_password != confirm_password:
        return settings_response(request, error="两次输入的新密码不一致", status_code=400)
    set_web_password(config, hash_password(new_password))
    config = load_config(CONFIG_PATH, create=False)
    logger.info("User action: update Web password")
    response = RedirectResponse("/login?message=Web密码已更新，请重新登录", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.post("/settings/scheduler")
async def save_scheduler_settings(
    request: Request,
    daily_time: Annotated[str, Form()],
    jitter_min: Annotated[int, Form()],
    jitter_max: Annotated[int, Form()],
    retry_delay_minutes: Annotated[int, Form()],
    max_retries: Annotated[int, Form()],
    max_concurrency: Annotated[int, Form()],
    keepalive_interval_hours: Annotated[int, Form()],
    csrf_form_token: Annotated[str, Form(alias="csrf_token")],
    enabled: Annotated[str | None, Form()] = None,
    _: None = Depends(require_auth),
):
    global config
    require_csrf(csrf_form_token)
    try:
        update_scheduler_settings(
            config,
            enabled=enabled == "1",
            daily_time=daily_time,
            jitter_seconds=(jitter_min, jitter_max),
            retry_delay_minutes=retry_delay_minutes,
            max_retries=max_retries,
            max_concurrency=max_concurrency,
            keepalive_interval_hours=keepalive_interval_hours,
        )
    except (ValueError, OSError) as error:
        return settings_response(request, error=f"调度器配置保存失败：{error}", status_code=400)
    config = load_config(CONFIG_PATH, create=False)
    scheduler_service.reconfigure(config)
    logger.info(
        "User action: update scheduler; enabled=%s daily_time=%s keepalive=%sh",
        config.scheduler.enabled,
        config.scheduler.daily_time,
        config.scheduler.keepalive_interval_hours,
    )
    return RedirectResponse("/settings?message=调度器配置已保存并立即生效", status_code=303)


@app.get("/accounts")
async def accounts_page(request: Request, _: None = Depends(require_auth)):
    data = account_summaries(DATABASE_PATH, 90)
    accounts = load_accounts(ACCOUNTS_PATH)
    account_meta = {account.id: account.label for account in accounts}
    account_meta_avatar = {account.id: account.avatar_url for account in accounts}
    account_meta_expiry = {account.id: token_expiry_text(account.token_expires_at) for account in accounts}
    known_ids = {item["account_id"] for item in data}
    for account in accounts:
        if account.id not in known_ids:
            data.append(
                {
                    "account_id": account.id,
                    "last_run": None,
                    "successful": 0,
                    "already_signed": 0,
                    "signed_count": 0,
                    "failed": 0,
                    "token_invalid": 0,
                    "reward_total": 0,
                    "latest_balance": None,
                    "calendar": [],
                    "balance_history": [],
                    "avatar_url": account.avatar_url,
                    "token_expiry": account_meta_expiry[account.id],
                }
            )
    for item in data:
        item["avatar_url"] = account_meta_avatar.get(item["account_id"], "")
        item["token_expiry"] = account_meta_expiry.get(item["account_id"], "未知")
    return templates.TemplateResponse(
        request,
        "accounts.html",
        {
            "accounts": data,
            "account_meta": account_meta,
            "account_meta_avatar": account_meta_avatar,
            "csrf_token": csrf_token(config.web.session_secret),
        },
    )


@app.post("/dashboard/api/auth/start")
async def start_auth(
    request: AuthStartRequest,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    _: None = Depends(require_auth),
):
    require_csrf(csrf_header)
    accounts = load_accounts(ACCOUNTS_PATH)
    account_id = request.account_id.strip()
    if not account_id:
        account_id = f"account-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account_id):
        raise HTTPException(status_code=400, detail="Account ID may contain letters, numbers, underscore and hyphen only")
    label = request.label.strip() or next(
        (account.label for account in accounts if account.id == account_id),
        account_id,
    )
    action = "重新授权" if request.account_id.strip() else "添加账号"
    logger.info("User action: %s, account_id=%s", action, account_id)
    flow_id = auth_flow_manager.start(account_id, label, f"{config.site.base_url}/home")
    return JSONResponse({"flow_id": flow_id, "account_id": account_id})


@app.get("/dashboard/api/auth/status/{flow_id}")
async def auth_status(flow_id: str, _: None = Depends(require_auth)):
    status = auth_flow_manager.status(flow_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Authorization flow not found")
    return JSONResponse(vars(status))


@app.get("/dashboard/api/summary")
async def api_summary(days: int = 30, _: None = Depends(require_auth)):
    return JSONResponse(summary(DATABASE_PATH, days))


@app.post("/dashboard/api/accounts/{account_id}/balance/refresh")
async def refresh_balance(
    account_id: str,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    _: None = Depends(require_auth),
):
    require_csrf(csrf_header)
    account = next((item for item in load_accounts(ACCOUNTS_PATH) if item.id == account_id), None)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    logger.info("User action: refresh balance, account_id=%s", account_id)
    try:
        result = sync_account(
            ACCOUNTS_PATH,
            DATABASE_PATH,
            account.id,
            YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language),
            account.token,
        )
        if result.balance is None:
            raise RuntimeError("Balance is missing from user information response")
        captured_at = record_balance_snapshot(DATABASE_PATH, result.account_id, result.balance)
    except Exception as error:
        logger.warning("Balance refresh failed for %s", account_id, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Balance refresh failed: {error}") from error
    logger.info(
        "User action completed: refresh balance, account_id=%s, balance=%s",
        result.account_id,
        result.balance,
    )
    return JSONResponse(
        {
            "account_id": result.account_id,
            "name": result.label,
            "balance": result.balance,
            "updated_at": local_time_text(captured_at),
            "token_expires_at": token_expiry_text(result.token_expires_at),
        }
    )


@app.get("/dashboard/api/accounts")
async def api_accounts(_: None = Depends(require_auth)):
    return JSONResponse(account_summaries(DATABASE_PATH, 90))


@app.get("/dashboard/api/runs")
async def api_runs(days: int = 30, _: None = Depends(require_auth)):
    return JSONResponse(runs(DATABASE_PATH, days))


@app.get("/dashboard/api/logs")
async def api_logs(
    limit: int = 300,
    level: str = "",
    category: str = "",
    _: None = Depends(require_auth),
):
    data = runtime_logs(DATABASE_PATH, limit=limit, level=level, category=category)
    for item in data:
        item["created_at"] = local_time_text(item["created_at"])
    return JSONResponse(data)


@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler_service.shutdown()

