import builtins
import importlib
import sys

from tools.ydtv_wechat_login import extract_callback


def test_extract_wechat_callback():
    callback = "https://lingkeai.ai/weixin-callback?code=abc123&state=state456"
    assert extract_callback(callback) == callback


def test_extract_rejects_other_urls():
    assert extract_callback("https://ydtv.ai/home?code=abc") == ""
    assert extract_callback("https://lingkeai.ai/weixin-callback?state=x") == ""


def test_module_imports_without_tkinter(monkeypatch):
    """CI 的 Linux 环境可能没有 tkinter，导入模块不应失败。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ImportError("No module named 'tkinter'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for name in [key for key in sys.modules if key.startswith("tools.ydtv_wechat_login")]:
        del sys.modules[name]

    module = importlib.import_module("tools.ydtv_wechat_login")

    callback = "https://lingkeai.ai/weixin-callback?code=abc123"
    assert module.extract_callback(callback) == callback
