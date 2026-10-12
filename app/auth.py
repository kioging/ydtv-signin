from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request


COOKIE_NAME = "ydtv_panel_session"


@dataclass
class LoginRateLimiter:
    max_failures: int = 5
    lockout_seconds: int = 600
    failures: dict[str, list[int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = {}

    def is_blocked(self, key: str) -> bool:
        now = int(time.time())
        values = [stamp for stamp in self.failures.get(key, []) if now - stamp < self.lockout_seconds]
        self.failures[key] = values
        return len(values) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self.failures.setdefault(key, []).append(int(time.time()))

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash:
        return False
    try:
        PasswordHasher().verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_cookie(secret: str, ttl_hours: int) -> str:
    expires = int(time.time()) + ttl_hours * 3600
    nonce = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16]
    payload = f"{expires}.{nonce}"
    return f"{payload}.{_sign(secret, payload)}"


def validate_session_cookie(secret: str, cookie: str) -> bool:
    parts = cookie.split(".")
    if len(parts) != 3:
        return False
    expires, nonce, signature = parts
    if not expires.isdigit() or int(expires) < time.time():
        return False
    expected = _sign(secret, f"{expires}.{nonce}")
    return hmac.compare_digest(signature, expected)


def csrf_token(secret: str) -> str:
    return _sign(secret, "csrf-token")


def validate_csrf_token(secret: str, token: str) -> bool:
    return bool(secret and token and hmac.compare_digest(token, csrf_token(secret)))


def is_secure_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


async def is_authenticated(request: Request, secret: str) -> bool:
    cookie = request.cookies.get(COOKIE_NAME)
    return bool(cookie and secret and validate_session_cookie(secret, cookie))


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return "[REDACTED]" if len(value) > 8 else "[REDACTED]"
    return "[REDACTED]"

