#!/usr/bin/env bash
# 把面板注册为 systemd 服务（开机自启、进程崩溃自动重启）。
#
# 用法：
#   sudo bash install-service.sh
#   sudo SERVICE_USER=ydtv bash install-service.sh    # 指定运行用户（默认 root）
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="ydtv-signin"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请用 root 运行：sudo bash install-service.sh" >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "当前系统没有 systemd，无法注册服务；可以直接用 bash start.sh 前台运行。" >&2
  exit 1
fi

# 手动启动的旧进程会占用 8848 端口，先结束它
if pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "检测到手动启动的 ${SERVICE_NAME}，先结束它…"
  pkill -TERM -x "${SERVICE_NAME}" || true
  sleep 2
  pkill -KILL -x "${SERVICE_NAME}" 2>/dev/null || true
fi

cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=ydtv.ai sign-in panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory="${APP_DIR}"
Environment="YDTV_DATA_DIR=${APP_DIR}"
ExecStart="${APP_DIR}/${SERVICE_NAME}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
if ! systemctl restart "${SERVICE_NAME}"; then
  echo "systemctl restart 执行失败，最近日志：" >&2
  journalctl -u "${SERVICE_NAME}" -n 20 --no-pager >&2 || true
  exit 1
fi
sleep 2
if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
  echo "服务启动失败，最近日志：" >&2
  journalctl -u "${SERVICE_NAME}" -n 20 --no-pager >&2 || true
  exit 1
fi
systemctl status "${SERVICE_NAME}" --no-pager -l | head -n 12 || true

echo
echo "已安装并启动 ${SERVICE_NAME}.service（运行用户：${SERVICE_USER}）"
echo "常用命令： systemctl status|stop|restart ${SERVICE_NAME}"
if [[ "${SERVICE_USER}" != "root" ]]; then
  echo "提示：请确认 ${SERVICE_USER} 能写入 ${APP_DIR}（config.json / accounts.json / data / logs），必要时执行："
  echo "      chown -R ${SERVICE_USER}:${SERVICE_USER} ${APP_DIR}"
fi
