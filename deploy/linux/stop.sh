#!/usr/bin/env bash
# 停止 ydtv.ai 签到面板。
# 已安装 systemd 服务时走 systemctl，否则按进程名结束手动启动的实例。
set -uo pipefail

SERVICE_NAME="ydtv-signin"

if command -v systemctl >/dev/null 2>&1 && systemctl cat "${SERVICE_NAME}.service" >/dev/null 2>&1; then
  if ! systemctl stop "${SERVICE_NAME}"; then
    echo "systemctl stop 执行失败（可能需要 root 权限）" >&2
    exit 1
  fi
  if ! pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1; then
    echo "已通过 systemd 停止 ${SERVICE_NAME}"
    exit 0
  fi
  echo "systemd 服务已停止，但仍有 ${SERVICE_NAME} 进程在运行，继续结束…"
fi

if ! pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "${SERVICE_NAME} 未在运行"
  exit 0
fi

pkill -TERM -x "${SERVICE_NAME}" || true
for _ in $(seq 1 20); do
  pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1 || break
  sleep 0.5
done
if pgrep -x "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "进程未退出，强制结束"
  pkill -KILL -x "${SERVICE_NAME}" || true
fi
echo "${SERVICE_NAME} 已停止"
