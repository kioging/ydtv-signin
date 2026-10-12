from tools.ydtv_wechat_login import extract_callback


def test_extract_wechat_callback():
    callback = "https://lingkeai.ai/weixin-callback?code=abc123&state=state456"
    assert extract_callback(callback) == callback


def test_extract_rejects_other_urls():
    assert extract_callback("https://ydtv.ai/home?code=abc") == ""
    assert extract_callback("https://lingkeai.ai/weixin-callback?state=x") == ""
