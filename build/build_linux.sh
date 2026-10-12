#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  python3.11 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements-build.txt

.venv/bin/python -m PyInstaller --noconfirm --clean ydtv-signin.spec
mkdir -p release
HELPER_ARGS=()
if [[ -n "${YDTV_WECHAT_HELPER_EXE:-}" && -f "${YDTV_WECHAT_HELPER_EXE}" ]]; then
  HELPER_ARGS=(--helper-exe "${YDTV_WECHAT_HELPER_EXE}")
fi
.venv/bin/python build/package_release.py \
  --dist dist/ydtv-signin \
  --output release \
  --platform linux \
  "${HELPER_ARGS[@]}"
printf 'Release package created in %s/release\n' "$ROOT"

