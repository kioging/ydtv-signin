from __future__ import annotations

import json
import getpass
import logging
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteConfig:
    base_url: str = "https://ydtv.ai"
    api_prefix: str = "/houduan"
    language: str = "zh"
    timezone: str = "Asia/Shanghai"


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = True
    daily_time: str = "09:05"
    jitter_seconds: tuple[int, int] = (60, 600)
    retry_delay_minutes: int = 30
    max_retries: int = 3
    max_concurrency: int = 1
    keepalive_interval_hours: int = 6


@dataclass(frozen=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8848
    password_hash: str = ""
    session_secret: str = ""
    session_ttl_hours: int = 12
    tls_certfile: str = ""
    tls_keyfile: str = ""
    security_headers: str = "auto"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    retention_days: int = 180


@dataclass(frozen=True)
class AppConfig:
    site: SiteConfig
    scheduler: SchedulerConfig
    web: WebConfig
    logging: LoggingConfig
    config_path: Path
    data_dir: Path


DEFAULT_CONFIG: dict[str, Any] = {
    "site": {
        "base_url": "https://ydtv.ai",
        "api_prefix": "/houduan",
        "language": "zh",
        "timezone": "Asia/Shanghai",
    },
    "scheduler": {
        "enabled": True,
        "daily_time": "09:05",
        "jitter_seconds": [60, 600],
        "retry_delay_minutes": 30,
        "max_retries": 3,
        "max_concurrency": 1,
        "keepalive_interval_hours": 6,
    },
    "web": {
        "host": "0.0.0.0",
        "port": 8848,
        # 默认密码 admin123（Argon2id）。首次登录后请立刻在「设置」页修改，
        # 或者执行 `./ydtv-signin set-password` 重置。
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$yIqbypra6gDOF6ibOGTBXA$QHazAxRXJ3TGm4EBcT9Pw0UxpKTRL+W5Y++4msRKMfo",
        "session_secret": "",
        "session_ttl_hours": 12,
        "tls_certfile": "",
        "tls_keyfile": "",
        "security_headers": "auto",
    },
    "logging": {"level": "INFO", "retention_days": 180},
}


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def atomic_write_json(path: Path, value: dict[str, Any], *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            if os.name == "posix":
                os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            elif os.name == "nt":
                # Windows: remove inherited ACEs, then grant the current user full control.
                import subprocess

                result = subprocess.run(
                    ["icacls", str(temporary), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:(F)"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "Could not restrict permissions on %s: %s",
                        temporary,
                        (result.stderr or result.stdout).strip(),
                    )
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def create_default_config(path: Path) -> None:
    value = json.loads(json.dumps(DEFAULT_CONFIG))
    value["web"]["session_secret"] = secrets.token_hex(32)
    atomic_write_json(path, value, private=True)


def load_config(path: Path, *, create: bool = True) -> AppConfig:
    if not path.exists():
        if not create:
            raise FileNotFoundError(f"Configuration file not found: {path}")
        create_default_config(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config.json must contain a JSON object")
    data = _merge(DEFAULT_CONFIG, raw)

    site_raw = data["site"]
    scheduler_raw = data["scheduler"]
    web_raw = data["web"]
    logging_raw = data["logging"]
    jitter = tuple(scheduler_raw["jitter_seconds"])
    if len(jitter) != 2 or jitter[0] < 0 or jitter[1] < jitter[0]:
        raise ValueError("scheduler.jitter_seconds must be [min, max] with 0 <= min <= max")

    hour, minute = map(int, scheduler_raw["daily_time"].split(":", 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("scheduler.daily_time must be a valid HH:MM time")
    tls_certfile = str(web_raw["tls_certfile"] or "").strip()
    tls_keyfile = str(web_raw["tls_keyfile"] or "").strip()
    if bool(tls_certfile) != bool(tls_keyfile):
        raise ValueError("web.tls_certfile and web.tls_keyfile must be set together")
    security_headers = str(web_raw["security_headers"] or "auto").strip().lower()
    if security_headers not in {"auto", "always", "never"}:
        raise ValueError("web.security_headers must be one of: auto, always, never")

    return AppConfig(
        site=SiteConfig(
            base_url=str(site_raw["base_url"]).rstrip("/"),
            api_prefix=str(site_raw["api_prefix"]).rstrip("/"),
            language=str(site_raw["language"]),
            timezone=str(site_raw["timezone"]),
        ),
        scheduler=SchedulerConfig(
            enabled=bool(scheduler_raw["enabled"]),
            daily_time=str(scheduler_raw["daily_time"]),
            jitter_seconds=(int(jitter[0]), int(jitter[1])),
            retry_delay_minutes=int(scheduler_raw["retry_delay_minutes"]),
            max_retries=int(scheduler_raw["max_retries"]),
            max_concurrency=int(scheduler_raw["max_concurrency"]),
            keepalive_interval_hours=int(scheduler_raw["keepalive_interval_hours"]),
        ),
        web=WebConfig(
            host=str(web_raw["host"]),
            port=int(web_raw["port"]),
            password_hash=str(web_raw["password_hash"]),
            session_secret=str(web_raw["session_secret"]),
            session_ttl_hours=int(web_raw["session_ttl_hours"]),
            tls_certfile=tls_certfile,
            tls_keyfile=tls_keyfile,
            security_headers=security_headers,
        ),
        logging=LoggingConfig(
            level=str(logging_raw["level"]).upper(),
            retention_days=int(logging_raw["retention_days"]),
        ),
        config_path=path,
        data_dir=path.parent,
    )


def set_web_password(config: AppConfig, password_hash: str) -> str:
    raw = json.loads(config.config_path.read_text(encoding="utf-8"))
    session_secret = secrets.token_hex(32)
    raw.setdefault("web", {})["password_hash"] = password_hash
    raw["web"]["session_secret"] = session_secret
    atomic_write_json(config.config_path, raw, private=True)
    return session_secret


def update_scheduler_settings(
    config: AppConfig,
    *,
    enabled: bool,
    daily_time: str,
    jitter_seconds: tuple[int, int],
    retry_delay_minutes: int,
    max_retries: int,
    max_concurrency: int,
    keepalive_interval_hours: int,
) -> None:
    hour, minute = map(int, daily_time.split(":", 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("每日执行时间格式无效")
    if jitter_seconds[0] < 0 or jitter_seconds[1] < jitter_seconds[0]:
        raise ValueError("随机延迟范围无效")
    if retry_delay_minutes < 1 or max_retries < 0 or max_concurrency < 1:
        raise ValueError("重试或并发配置无效")
    if keepalive_interval_hours < 0:
        raise ValueError("Token 保活间隔不能小于 0")
    raw = json.loads(config.config_path.read_text(encoding="utf-8"))
    raw["scheduler"] = {
        "enabled": enabled,
        "daily_time": daily_time,
        "jitter_seconds": [jitter_seconds[0], jitter_seconds[1]],
        "retry_delay_minutes": retry_delay_minutes,
        "max_retries": max_retries,
        "max_concurrency": max_concurrency,
        "keepalive_interval_hours": keepalive_interval_hours,
    }
    atomic_write_json(config.config_path, raw, private=True)


def hash_password(password: str) -> str:
    return PasswordHasher().hash(password)

