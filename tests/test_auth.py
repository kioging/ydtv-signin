from starlette.requests import Request

from app.auth import (
    LoginRateLimiter,
    create_session_cookie,
    is_secure_request,
    validate_session_cookie,
    verify_password,
)
from app.config import hash_password


def test_password_and_session():
    password_hash = hash_password("a-strong-password-123")
    assert verify_password(password_hash, "a-strong-password-123")
    assert not verify_password(password_hash, "wrong")
    cookie = create_session_cookie("secret", 1)
    assert validate_session_cookie("secret", cookie)
    assert not validate_session_cookie("wrong", cookie)


def test_rate_limiter():
    limiter = LoginRateLimiter(max_failures=2, lockout_seconds=60)
    limiter.record_failure("ip")
    assert not limiter.is_blocked("ip")
    limiter.record_failure("ip")
    assert limiter.is_blocked("ip")


def _request(scheme: str = "http", forwarded_proto: str | None = None) -> Request:
    headers = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "scheme": scheme,
            "headers": headers,
            "client": ("203.0.113.5", 12345),
            "server": ("panel.example.com", 443 if scheme == "https" else 80),
            "query_string": b"",
        }
    )


def test_secure_request_detection():
    assert is_secure_request(_request("http")) is False
    assert is_secure_request(_request("https")) is True
    assert is_secure_request(_request("http", "https")) is True
    assert is_secure_request(_request("http", "https, http")) is True
    assert is_secure_request(_request("http", "http")) is False

