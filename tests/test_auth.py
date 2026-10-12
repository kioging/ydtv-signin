from app.auth import LoginRateLimiter, create_session_cookie, validate_session_cookie, verify_password
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

