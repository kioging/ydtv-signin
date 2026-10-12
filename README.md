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
- 微信登录：客户运行独立 Windows 登录助手，扫码后将回调地址粘贴回面板

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

## 独立 Windows 微信登录助手

面向客户的 Windows 助手单独打包，不连接服务器、不读取服务器文件：

```text
ydtv-wechat-login.exe
```

使用流程：

1. 在 Web 面板“添加账号 -> 微信登录”中点击“下载微信登录工具”
2. 运行下载的 `客户微信登录助手.exe`
3. 点击“开始微信登录”
4. 助手调用本机 Edge/Chrome 打开官方微信授权页
5. 用户扫码完成登录
6. 助手捕获完整回调地址并自动复制到剪贴板
7. 用户回到 Web 面板，在“添加账号 -> 微信登录”中粘贴回调地址并导入

客户端助手运行在客户电脑上，不读取服务器文件。服务器部署包会在 `downloads/` 中携带该 EXE，并通过需要登录的下载接口提供。

## 公网部署

服务默认监听 `0.0.0.0:8848`（HTTP），可通过本机和局域网地址访问。公网访问推荐用 Nginx/Caddy 终止 TLS，示例配置见：

- `deploy/nginx-https.conf.example`
- `deploy/Caddyfile.example`

登录 Cookie 的 `Secure` 标记是自适应的：通过 HTTPS 访问（或反向代理带上 `X-Forwarded-Proto: https`）时自动加 `Secure`，直接内网 HTTP 访问时不加，因此局域网和 HTTPS 部署都能正常保持登录状态。公网仍必须使用 HTTPS，否则密码和会话都会明文传输。

安全响应头（`X-Frame-Options`、CSP、HSTS）默认按运行方式自动启用：源码方式运行（本地测试）不发送，打包后的部署程序自动发送。可在 `config.json` 的 `web.security_headers` 中指定 `auto`（默认）、`always` 或 `never`。注意这些头会阻止 Codex 等内嵌浏览器注入批注浮层，如果需要在部署后的面板上批注，把它设为 `never`。

### 方式一：反向代理（推荐）

1. 修改 `config.json`，把 `web.host` 改成 `127.0.0.1`，避免 8848 端口直接暴露公网
2. 按 `deploy/nginx-https.conf.example` 或 `deploy/Caddyfile.example` 配置反向代理并启用证书
3. 如果反向代理和面板不在同一台机器，启动时设置 `FORWARDED_ALLOW_IPS`（uvicorn 默认只信任来自 `127.0.0.1` 的转发头）；同时确认代理传递 `X-Forwarded-For`，否则所有客户端都会被当成同一个 IP，登录限速会互相影响

反代示例不再重复下发 `X-Frame-Options`、CSP、HSTS 等头，统一由应用发送。如果用源码方式部署到公网（不是打包程序），请在 `config.json` 里把 `web.security_headers` 设为 `always`，否则不会下发这些安全头。

### 方式二：服务直接启用 HTTPS

如果不想额外跑反向代理，可以在 `config.json` 的 `web` 段直接指定证书：

```json
"web": {
  "host": "0.0.0.0",
  "port": 8848,
  "tls_certfile": "/etc/letsencrypt/live/your-domain.example.com/fullchain.pem",
  "tls_keyfile": "/etc/letsencrypt/live/your-domain.example.com/privkey.pem"
}
```

两个字段必须同时设置，留空表示继续用 HTTP；相对路径按程序所在目录解析。配置后访问 `https://your-domain.example.com:8848`。

## 二进制部署包

Windows 原生构建：

```powershell
.\build\build_windows.ps1
.\build\build_wechat_windows.ps1
```

Linux 原生构建：

```bash
bash build/build_linux.sh
```

CI 里的 Linux 包是在 `manylinux2014` 容器（CentOS 7 基础，glibc 2.17）中构建的，可在 CentOS 7 / Alibaba Cloud Linux 2/3、Ubuntu 16.04+ 等系统上直接运行（仅 x86_64）。只有在更老的 glibc（如 CentOS 6）上才会出现 `GLIBC_2.xx not found` 报错，那种情况建议改用源码 + systemd 部署。

Linux 部署包同样必须自带 Windows 的 `客户微信登录助手.exe`（客户下载后在自己电脑上运行）。构建脚本会依次从 `YDTV_WECHAT_HELPER_EXE`、`downloads/客户微信登录助手.exe`、`downloads/ydtv-wechat-login.exe`、`dist/ydtv-wechat-login.exe` 查找，找不到就直接报错；只有本地测试才用 `YDTV_ALLOW_MISSING_HELPER=1` 跳过。CI 会先构建 Windows 助手，再把 EXE 传给 Linux 打包任务。

构建结果位于：

- `release/ydtv-signin-windows-x64.zip`
- `release/ydtv-signin-linux-x64.zip`
- `release/ydtv-wechat-login-windows-x64.zip`

ZIP 中包含 FastAPI 运行时，不需要在服务器安装 Python，也不再包含 Playwright 或 Chromium。首次运行会生成 `config.json`。

**Web 面板默认密码是 `admin123`，登录后请立刻在「设置」页修改；公网部署前务必先改掉。** 也可以在启动前用下面的命令重置密码（会同时轮换会话密钥，必须重启服务后生效）：

```text
Windows:
  ydtv-signin.exe set-password
  start.bat            # 启动面板

Linux:
  ./ydtv-signin set-password
  ./start.sh           # 启动面板
```

PyInstaller 不支持 Windows/Linux 交叉编译。Windows 包需要在 Windows 构建，Linux 包需要在 Linux 构建。仓库中的 `.github/workflows/build-binaries.yml` 会在两个原生 runner 上分别生成 ZIP。

