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


def test_rate_limiter_blocks_globally_after_many_failures():
    limiter = LoginRateLimiter(max_failures=100, lockout_seconds=60, global_max_failures=3)
    for index in range(3):
        limiter.record_failure(f"10.0.0.{index}")
    assert limiter.is_globally_blocked() is True
    assert limiter.is_blocked("203.0.113.9") is False


def test_rate_limiter_global_flag_clears_after_window():
    limiter = LoginRateLimiter(max_failures=5, lockout_seconds=0, global_max_failures=3)
    for _ in range(5):
        limiter.record_failure("203.0.113.9")
    assert limiter.is_globally_blocked() is False


def test_rate_limiter_keeps_key_map_bounded():
    limiter = LoginRateLimiter(
        max_failures=5,
        lockout_seconds=60,
        global_max_failures=1000,
        max_keys=3,
    )
    for index in range(20):
        limiter.record_failure(f"10.0.1.{index}")
    assert len(limiter.failures) <= 3


def test_rate_limiter_reset_keeps_global_counter():
    limiter = LoginRateLimiter(max_failures=2, lockout_seconds=60, global_max_failures=100)
    limiter.record_failure("ip")
    limiter.reset("ip")
    assert "ip" not in limiter.failures
    assert limiter.is_blocked("ip") is False


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

