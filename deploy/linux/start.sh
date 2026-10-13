#!/usr/bin/env bash
# 前台启动 ydtv.ai 签到面板（日志直接输出到终端，Ctrl+C 停止）。
# 后台运行请用 restart.sh；注册成 systemd 服务请用 sudo bash install-service.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR}"
exec ./ydtv-signin
