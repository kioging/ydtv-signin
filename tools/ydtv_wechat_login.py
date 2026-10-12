from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from websockets.sync.client import connect as websocket_connect

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查使用
    import tkinter as tk


APP_TITLE = "ydtv.ai 微信登录助手"
AUTH_STATE_URL = "https://ydtv.ai/houduan/denglu/weixin/huoququanurl"


def load_tkinter():
    """Delay the GUI toolkit import so headless environments can import this module."""
    import tkinter

    return tkinter


def find_browser() -> str:
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
    raise FileNotFoundError("未找到 Microsoft Edge 或 Google Chrome。")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def request_auth_url() -> str:
    request = Request(
        AUTH_STATE_URL,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept-Language": "zh",
            "x-kongjian": "geren",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != 200:
        raise RuntimeError(str(payload.get("msg") or "微信授权地址获取失败"))
    auth_url = str((payload.get("data") or {}).get("authUrl") or "")
    if not auth_url:
        raise RuntimeError("微信授权地址为空")
    return auth_url


def wait_for_debug_port(port: int, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("浏览器调试端口未能启动")


def get_page_urls(port: int) -> list[str]:
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


def get_page_targets(port: int) -> list[dict]:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            return [
                item
                for item in json.loads(response.read().decode("utf-8"))
                if item.get("type") == "page"
            ]
    except Exception:
        return []


def extract_callback(url: str) -> str:
    parsed = urlparse(url)
    if "weixin-callback" not in parsed.path and "wechat-callback" not in parsed.path:
        return ""
    query = parse_qs(parsed.query)
    code = str((query.get("code") or [""])[0])
    return url if code else ""


def close_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()


def callback_from_cdp_message(message: str) -> str:
    try:
        payload = json.loads(message)
    except ValueError:
        return ""
    method = payload.get("method")
    params = payload.get("params") or {}
    if method == "Page.frameNavigated":
        return extract_callback(str((params.get("frame") or {}).get("url") or ""))
    if method == "Network.requestWillBeSent":
        return extract_callback(str((params.get("request") or {}).get("url") or ""))
    return ""


def capture_callback(port: int, timeout: float = 600) -> str:
    deadline = time.time() + timeout
    active: dict[str, object] = {}
    retry_at: dict[str, float] = {}
    commands = [
        json.dumps({"id": 1, "method": "Page.enable"}),
        json.dumps({"id": 2, "method": "Network.enable"}),
    ]
    try:
        while time.time() < deadline:
            for url in get_page_urls(port):
                callback = extract_callback(url)
                if callback:
                    return callback

            now = time.time()
            for target in get_page_targets(port):
                ws_url = str(target.get("webSocketDebuggerUrl") or "")
                if not ws_url or ws_url in active or now < retry_at.get(ws_url, 0):
                    continue
                try:
                    connection = websocket_connect(
                        ws_url,
                        open_timeout=1,
                        close_timeout=1,
                        proxy=None,
                    )
                    for command in commands:
                        connection.send(command)
                except Exception:
                    retry_at[ws_url] = now + 2
                    continue
                active[ws_url] = connection

            for ws_url, connection in list(active.items()):
                try:
                    message = connection.recv(timeout=0.2)
                except TimeoutError:
                    continue
                except Exception:
                    active.pop(ws_url, None)
                    retry_at[ws_url] = time.time() + 2
                    continue
                callback = callback_from_cdp_message(message)
                if callback:
                    return callback
            time.sleep(0.05)
        return ""
    finally:
        for connection in active.values():
            try:
                connection.close()
            except Exception:
                pass


class HelperApp:
    def __init__(self, root: tk.Tk) -> None:
        tk = load_tkinter()
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("680x360")
        self.root.minsize(620, 320)
        self.browser_process: subprocess.Popen | None = None
        self.profile_dir: Path | None = None
        self.running = False
        self.callback_url = ""

        frame = tk.Frame(root, padx=22, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=APP_TITLE,
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        self.status = tk.Label(
            frame,
            text="点击下方按钮开始微信登录",
            font=("Microsoft YaHei UI", 10),
            fg="#475569",
        )
        self.status.pack(anchor="w", pady=(10, 12))

        self.callback_text = tk.Text(frame, height=6, wrap="char", state="disabled")
        self.callback_text.pack(fill="x")

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=(14, 0))
        self.start_button = tk.Button(
            actions,
            text="开始微信登录",
            command=self.start_login,
            width=18,
            height=2,
        )
        self.start_button.pack(side="left")
        self.copy_button = tk.Button(
            actions,
            text="重新复制回调地址",
            command=self.copy_callback,
            state="disabled",
            width=20,
            height=2,
        )
        self.copy_button.pack(side="left", padx=(10, 0))

    def set_status(self, text: str, color: str = "#475569") -> None:
        self.status.configure(text=text, fg=color)

    def set_callback(self, callback_url: str) -> None:
        self.callback_url = callback_url
        self.callback_text.configure(state="normal")
        self.callback_text.delete("1.0", "end")
        self.callback_text.insert("1.0", callback_url)
        self.callback_text.configure(state="disabled")
        self.copy_button.configure(state="normal")

    def copy_callback(self) -> None:
        if not self.callback_url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.callback_url)
        self.root.update()
        self.set_status("回调地址已复制，请粘贴到 Web 面板。", "#166534")

    def start_login(self) -> None:
        if self.running:
            return
        self.running = True
        self.start_button.configure(state="disabled")
        self.set_callback("")
        self.set_status("正在启动本机浏览器…")
        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self) -> None:
        try:
            browser = find_browser()
            auth_url = request_auth_url()
            port = free_port()
            self.profile_dir = Path(tempfile.mkdtemp(prefix="ydtv-wechat-login-"))
            self.browser_process = subprocess.Popen(
                [
                    browser,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={self.profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--new-window",
                    auth_url,
                ]
            )
            self.root.after(0, self.set_status, "请在新窗口中完成微信扫码登录…")
            wait_for_debug_port(port)
            callback_url = capture_callback(port)
            if not callback_url:
                raise TimeoutError("等待微信登录超时")
            self.root.after(0, self.set_callback, callback_url)
            self.root.after(0, self.copy_callback)
        except Exception as error:
            self.root.after(0, self.set_status, f"登录失败：{error}", "#b42318")
        finally:
            if self.browser_process is not None:
                close_process_tree(self.browser_process)
            if self.profile_dir is not None:
                shutil.rmtree(self.profile_dir, ignore_errors=True)
            self.browser_process = None
            self.profile_dir = None
            self.running = False
            self.root.after(0, lambda: self.start_button.configure(state="normal"))


def main() -> int:
    tk = load_tkinter()
    root = tk.Tk()
    HelperApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
