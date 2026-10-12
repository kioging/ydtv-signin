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

    import httpx

    client = YdtvClient("https://example.com", "/api", "zh", transport=FakeTransport())
    response = client.verify_token("secret-token", "geren")
    assert response.status_code == 200
    assert captured["headers"]["x-kongjian"] == "geren"
    assert captured["headers"]["Accept-Language"] == "zh"
    assert "secret-token" not in str(captured["headers"])
    assert captured["url"].endswith("/api/user/tokenyanzheng")

