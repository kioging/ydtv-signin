#!/usr/bin/env bash
# 卸载 systemd 服务。只删除服务定义，保留 config.json / accounts.json / data / logs。
set -euo pipefail

SERVICE_NAME="ydtv-signin"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请用 root 运行：sudo bash uninstall-service.sh" >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
fi

if [[ -f "${SERVICE_FILE}" ]]; then
  rm -f "${SERVICE_FILE}"
  echo "已删除 ${SERVICE_FILE}"
else
  echo "未找到 ${SERVICE_FILE}（可能尚未安装）"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
fi

echo "服务已卸载；config.json、accounts.json、data/、logs/ 均已保留。"
