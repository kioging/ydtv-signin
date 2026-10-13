#!/usr/bin/env bash
# 重启 ydtv.ai 签到面板。
# 已安装 systemd 服务时走 systemctl restart，否则先停止旧进程再后台启动。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="ydtv-signin"

if command -v systemctl >/dev/null 2>&1 && systemctl cat "${SERVICE_NAME}.service" >/dev/null 2>&1; then
  if ! systemctl restart "${SERVICE_NAME}"; then
    echo "systemctl restart 执行失败（可能需要 root 权限）" >&2
    exit 1
  fi
  systemctl status "${SERVICE_NAME}" --no-pager -l | head -n 12 || true
  exit 0
fi

bash "${APP_DIR}/stop.sh"
mkdir -p "${APP_DIR}/logs"
cd "${APP_DIR}"
nohup "./${SERVICE_NAME}" >>"${APP_DIR}/logs/ydtv-signin.log" 2>&1 &
pid=$!
sleep 2
if ! pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "${SERVICE_NAME} 启动失败，日志末尾：" >&2
  tail -n 20 "${APP_DIR}/logs/ydtv-signin.log" >&2 || true
  exit 1
fi
echo "${SERVICE_NAME} 已在后台启动，PID ${pid}"
echo "日志文件：${APP_DIR}/logs/ydtv-signin.log"
