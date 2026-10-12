from app.wechat_login import extract_callback


def test_extract_wechat_callback():
    result = extract_callback(
        "https://lingkeai.ai/weixin-callback?code=abc123&state=state456"
    )
    assert result == ("abc123", "state456")


def test_extract_wechat_callback_rejects_other_urls():
    assert extract_callback("https://ydtv.ai/home?code=abc") is None
    assert extract_callback("https://lingkeai.ai/weixin-callback?state=x") is None
