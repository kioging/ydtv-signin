from fastapi.testclient import TestClient


def test_health_and_auth_redirect(tmp_path, monkeypatch):
    monkeypatch.setenv("YDTV_DATA_DIR", str(tmp_path))
    import app.main as main

    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 401
    login = client.get("/login")
    assert login.status_code == 200
