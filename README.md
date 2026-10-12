# ydtv.ai 自动签到服务

基于 Python FastAPI 的 ydtv.ai 多账号每日签到服务，内置密码保护的 Web 状态面板。

## 安装

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Linux/macOS:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 初始化

1. 启动一次服务生成 `config.json`:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8848
```

2. 设置 Web 访问密码（至少 16 位）:

```bash
.venv/bin/python -m app.cli set-password
```

3. 打开面板 `/accounts`，点击“添加账号”。面板支持四种登录方式：

- 密码登录：输入账号、密码和图形验证码
- 手机登录：输入手机号、图形验证码和短信验证码
- 邮箱登录：输入邮箱、图形验证码和邮箱验证码
- 微信登录：面板打开官方微信授权窗口，完成登录后将最终回调地址粘贴回面板

密码、手机、邮箱登录不依赖浏览器自动化。微信登录也仅使用普通浏览器完成官方 OAuth，不需要 Playwright 或 Chromium。

重复登录同一个 ydtv.ai 用户时会根据用户 ID 覆盖原 Token，不会重复添加账号。

4. 导入账号:

```bash
.venv/bin/python -m app.cli account add main
.venv/bin/python -m app.cli account test
```

Windows 下将 `.venv/bin` 替换为 `.venv\Scripts`。

## 启动

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8848
```

默认每天 09:05（Asia/Shanghai）执行，支持失败自动重试。面板地址:

- `/`: 总览
- `/accounts`: 账号、日历和余额
- `/history`: 运行历史
- `/logs`: 后端运行日志、ydtv.ai 请求和 Web 操作审计
- `/settings`: Web 密码和调度器配置

## 独立微信登录助手

如果不想在网页中手动粘贴回调地址，可以运行独立助手。它会调用本机已安装的 Edge/Chrome，不依赖 Playwright：

```powershell
.\.venv\Scripts\python.exe wechat_login.py
```

或：

```powershell
.\.venv\Scripts\python.exe -m app.wechat_login
```

登录成功后助手会自动捕获微信回调地址、兑换 Token、导入账号并保存到 `accounts.json`。使用 `--no-import` 可以只获取回调地址：

```powershell
.\.venv\Scripts\python.exe wechat_login.py --no-import
```

## 公网部署

服务默认监听 `0.0.0.0`，可通过本机和局域网地址访问。公网访问请使用 Nginx/Caddy 反向代理并启用 HTTPS，否则 Cookie 的 `Secure` 标记会导致登录状态无法保存。

## 二进制部署包

Windows 原生构建：

```powershell
.\build\build_windows.ps1
```

Linux 原生构建：

```bash
bash build/build_linux.sh
```

构建结果位于：

- `release/ydtv-signin-windows-x64.zip`
- `release/ydtv-signin-linux-x64.zip`

ZIP 中包含 FastAPI 运行时，不需要在服务器安装 Python，也不再包含 Playwright 或 Chromium。首次运行会生成 `config.json`。使用方式：

```text
Windows:
  ydtv-signin.exe set-password
  ydtv-signin.exe wechat-login
  start.bat

Linux:
  ./ydtv-signin set-password
  ./ydtv-signin wechat-login
  ./start.sh
```

PyInstaller 不支持 Windows/Linux 交叉编译。Windows 包需要在 Windows 构建，Linux 包需要在 Linux 构建。仓库中的 `.github/workflows/build-binaries.yml` 会在两个原生 runner 上分别生成 ZIP。

