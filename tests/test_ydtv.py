import httpx

from app.ydtv import YdtvClient, encode_token


def test_encode_token_stable():
    assert encode_token("abc").endswith("=")


def test_default_api_prefix():
    client = YdtvClient()
    assert client._url("/user/tokenyanzheng") == "https://ydtv.ai/houduan/user/tokenyanzheng"


def test_client_headers(monkeypatch):
    captured = {}

    class FakeTransport:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def handle_request(self, request):
            captured.update(headers=request.headers, url=str(request.url))
            return httpx.Response(200, json={"code": 200})

    client = YdtvClient("https://example.com", "/api", "zh", transport=FakeTransport())
    response = client.verify_token("secret-token", "geren")
    assert response.status_code == 200
    assert captured["headers"]["x-kongjian"] == "geren"
    assert captured["headers"]["Accept-Language"] == "zh"
    assert "secret-token" not in str(captured["headers"])
    assert captured["url"].endswith("/api/user/tokenyanzheng")


def test_password_login_payload_does_not_send_plain_password():
    captured = {}

    class FakeTransport:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def handle_request(self, request):
            captured["body"] = request.content.decode("utf-8")
            captured["headers"] = request.headers
            return httpx.Response(200, json={"code": 4001, "msg": "captcha"})

    client = YdtvClient("https://example.com", "/houduan", "zh", transport=FakeTransport())
    client.login_password("user@example.com", "plain-password", "captcha-id", "1234")
    assert "plain-password" not in captured["body"]
    assert '"账号":"user@example.com"' in captured["body"]
    assert "token" not in captured["headers"]


def test_wechat_auth_url_payload():
    captured = {}

    class FakeTransport:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def handle_request(self, request):
            captured["url"] = str(request.url)
            captured["body"] = request.content.decode("utf-8")
            return httpx.Response(200, json={"code": 200, "data": {"authUrl": "https://example.com"}})

    client = YdtvClient("https://example.com", "/houduan", "zh", transport=FakeTransport())
    client.get_wechat_auth_url("ydtv.ai")
    assert captured["url"].endswith("/houduan/denglu/weixin/huoququanurl")
    assert "ydtv.ai" in captured["body"]

