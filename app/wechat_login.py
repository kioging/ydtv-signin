from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from .account_sync import sync_account
from .config import load_config
from .ydtv import YdtvClient


def find_browser(explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Browser not found: {path}")
        return str(path)

    candidates: list[str] = []
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", "")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
        candidates.extend(
            [
                str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
                str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
                str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe"),
            ]
        )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        )
    else:
        candidates.extend(
            [
                "microsoft-edge",
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
            ]
        )

    for candidate in candidates:
        if not candidate:
            continue
        found = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if found and Path(found).exists():
            return found
    raise FileNotFoundError(
        "未找到 Edge/Chrome。请安装浏览器，或使用 --browser-path 指定浏览器路径。"
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_debug_port(port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("浏览器调试端口未能启动")


def page_urls(port: int) -> list[str]:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            pages = json.loads(response.read().decode("utf-8"))
        return [
            str(item.get("url") or "")
            for item in pages
            if item.get("type") == "page"
        ]
    except Exception:
        return []


def extract_callback(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    code = str((query.get("code") or [""])[0])
    state = str((query.get("state") or [""])[0])
    if not code:
        return None
    if "weixin-callback" not in parsed.path and "wechat-callback" not in parsed.path:
        return None
    return code, state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ydtv.ai 微信登录助手（不使用 Playwright）")
    parser.add_argument("--root", help="项目数据目录")
    parser.add_argument("--account-id", help="导入后使用的账号 ID")
    parser.add_argument("--browser-path", help="Edge/Chrome 可执行文件路径")
    parser.add_argument("--timeout", type=int, default=300, help="等待登录的超时秒数")
    parser.add_argument("--no-import", action="store_true", help="只输出回调地址，不写入账号")
    parser.add_argument("--keep-browser", action="store_true", help="完成后保留浏览器")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path.cwd()
    config = load_config(root / "config.json")
    browser = find_browser(args.browser_path)
    port = free_port()
    profile = root / ".wechat-login-profile"
    profile.mkdir(parents=True, exist_ok=True)

    domain = urlparse(config.site.base_url).hostname or "ydtv.ai"
    client = YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language)
    response = client.get_wechat_auth_url(domain)
    if response.status_code != 200 or response.payload.get("code") != 200:
        print(f"获取微信授权地址失败：{response.payload}", file=sys.stderr)
        return 1
    auth_url = str((response.payload.get("data") or {}).get("authUrl") or "")
    if not auth_url:
        print("微信授权地址为空。", file=sys.stderr)
        return 1

    process = subprocess.Popen(
        [
            browser,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--new-window",
            auth_url,
        ]
    )
    print(f"已使用本机浏览器打开微信登录窗口：{browser}")
    print("请完成微信扫码登录，程序会自动捕获回调地址。")

    callback_url = ""
    try:
        wait_for_debug_port(port, timeout=15)
        deadline = time.time() + max(args.timeout, 30)
        while time.time() < deadline:
            if process.poll() is not None:
                print("浏览器已关闭，微信登录未完成。", file=sys.stderr)
                return 1
            for url in page_urls(port):
                parsed = extract_callback(url)
                if parsed:
                    callback_url = url
                    break
            if callback_url:
                break
            time.sleep(0.1)

        if not callback_url:
            print("等待微信登录超时。", file=sys.stderr)
            return 1

        callback_file = root / "data" / "wechat_callback.txt"
        callback_file.parent.mkdir(parents=True, exist_ok=True)
        callback_file.write_text(callback_url + "\n", encoding="utf-8")
        print(f"回调地址：{callback_url}")
        print(f"已保存：{callback_file}")

        if args.no_import:
            return 0

        code, _state = extract_callback(callback_url) or ("", "")
        login_response = client.login_wechat(code, domain)
        if login_response.status_code != 200 or login_response.payload.get("code") != 200:
            print(f"微信登录换 Token 失败：{login_response.payload}", file=sys.stderr)
            return 1
        data = login_response.payload.get("data") or {}
        token = str(data.get("token") or "")
        if not token:
            print("登录响应未返回 Token。", file=sys.stderr)
            return 1

        account_id = args.account_id or f"wechat-{uuid.uuid4().hex[:8]}"
        result = sync_account(
            root / "accounts.json",
            root / "data" / "signin.db",
            account_id,
            client,
            token,
        )
        action = "新增" if result.created else "覆盖"
        print(f"账号{action}成功：{result.label} ({result.account_id})")
        print(f"账户余额：{result.balance if result.balance is not None else '未知'}")
        print(f"Token 有效期：{result.token_expires_at or '未知'}")
        return 0
    finally:
        if not args.keep_browser and process.poll() is None:
            process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
