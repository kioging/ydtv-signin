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
