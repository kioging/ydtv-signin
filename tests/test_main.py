import dataclasses
import sys

from fastapi.testclient import TestClient


def test_health_and_auth_redirect(tmp_path, monkeypatch):
    monkeypatch.setenv("YDTV_DATA_DIR", str(tmp_path))
    import app.main as main
    from app.accounts import Account, load_accounts, save_accounts
    from app.auth import COOKIE_NAME, create_session_cookie, csrf_token

    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 401
    login = client.get("/login")
    assert login.status_code == 200
    # 面板必须允许被 Codex 等内嵌浏览器加载并注入批注浮层，否则批注不可用。
    assert "x-frame-options" not in login.headers
    assert "content-security-policy" not in login.headers
    assert login.headers["x-content-type-options"] == "nosniff"
    assert login.headers["referrer-policy"] == "no-referrer"
    # 登出必须是 POST + CSRF，避免第三方页面用 GET 诱导退出。
    get_logout = client.get("/logout", follow_redirects=False)
    assert get_logout.status_code == 405
    wrong_csrf = client.post("/logout", data={"csrf_token": "not-a-token"}, follow_redirects=False)
    assert wrong_csrf.status_code == 403
    post_logout = client.post(
        "/logout",
        data={"csrf_token": csrf_token(main.config.web.session_secret)},
        follow_redirects=False,
    )
    assert post_logout.status_code == 303
    assert post_logout.headers["location"] == "/login"

    # 打包部署（frozen）时 auto 模式会自动启用完整安全头。
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen_login = client.get("/login")
    assert frozen_login.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in frozen_login.headers["content-security-policy"]
    monkeypatch.delattr(sys, "frozen")

    # 也可以在 config.json 里强制开启或关闭。
    forced = dataclasses.replace(
        main.config,
        web=dataclasses.replace(main.config.web, security_headers="always"),
    )
    monkeypatch.setattr(main, "config", forced)
    forced_login = client.get("/login")
    assert forced_login.headers["x-frame-options"] == "DENY"

    main.WECHAT_HELPER_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    main.WECHAT_HELPER_FALLBACK_PATH.write_bytes(b"MZ-test-helper")
    save_accounts(main.ACCOUNTS_PATH, [Account(id="a", label="A", token="token-a")])
    client.cookies.set(
        COOKIE_NAME,
        create_session_cookie(main.config.web.session_secret, main.config.web.session_ttl_hours),
    )
    download = client.get("/downloads/wechat-helper")
    assert download.status_code == 200
    assert download.content == b"MZ-test-helper"
    delete = client.post(
        "/dashboard/api/accounts/a/delete",
        headers={"X-CSRF-Token": csrf_token(main.config.web.session_secret)},
    )
    assert delete.status_code == 200
    assert load_accounts(main.ACCOUNTS_PATH) == []

    # 全局限流只拦截错误密码，正确密码仍然可以登录（避免被分布式尝试锁死）。
    from app.config import hash_password

    secured = dataclasses.replace(
        main.config,
        web=dataclasses.replace(main.config.web, password_hash=hash_password("secret-password")),
    )
    monkeypatch.setattr(main, "config", secured)
    main.rate_limiter.failures.clear()
    for index in range(main.rate_limiter.global_max_failures):
        main.rate_limiter.record_failure(f"10.9.0.{index}")
    assert main.rate_limiter.is_globally_blocked() is True

    client.cookies.clear()
    wrong = client.post("/login", data={"password": "wrong-password"}, follow_redirects=False)
    assert wrong.status_code == 429
    correct = client.post("/login", data={"password": "secret-password"}, follow_redirects=False)
    assert correct.status_code == 303
