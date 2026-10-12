# ydtv.ai 自动签到服务

基于 Python FastAPI 的 ydtv.ai 多账号每日签到服务，内置密码保护的 Web 状态面板。

## 安装

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

Linux/macOS:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
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

3. 打开面板 `/accounts`，点击“授权登录”。服务会打开一个受控浏览器窗口，你在其中扫码或输入账号密码后，服务会自动保存 Token。

每个账号使用独立的浏览器 profile（`.auth-profile/<account-id>/`），因此可以依次添加多个不同账号。重复登录同一个 ydtv.ai 用户时会自动覆盖原 Token，不会重复添加。

### 长期服务授权

如果 Web 服务作为 systemd、NSSM 或后台进程运行，它通常不能直接显示登录窗口。请在需要授权的用户桌面终端中运行：

```bash
.venv/bin/python -m app.cli account authorize
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m app.cli account authorize
```

授权助手会在当前桌面打开浏览器，完成登录后直接更新同一份 `accounts.json` 和数据库。

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

ZIP 中包含 FastAPI、Playwright 驱动和对应平台的 Chromium，不需要在服务器安装 Python。首次运行会生成 `config.json`。使用方式：

```text
Windows:
  ydtv-signin.exe set-password
  ydtv-signin.exe account authorize
  start.bat

Linux:
  ./ydtv-signin set-password
  ./ydtv-signin account authorize
  ./start.sh
```

PyInstaller 不支持 Windows/Linux 交叉编译。Windows 包需要在 Windows 构建，Linux 包需要在 Linux 构建。仓库中的 `.github/workflows/build-binaries.yml` 会在两个原生 runner 上分别生成 ZIP。

