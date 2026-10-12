#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-build.txt

.venv/bin/python -m PyInstaller --noconfirm --clean ydtv-signin.spec
mkdir -p release

HELPER_ARGS=()
HELPER_EXE="${YDTV_WECHAT_HELPER_EXE:-}"
if [[ -z "$HELPER_EXE" ]]; then
  for candidate in "downloads/客户微信登录助手.exe" "downloads/ydtv-wechat-login.exe" "dist/ydtv-wechat-login.exe"; do
    if [[ -f "$candidate" ]]; then
      HELPER_EXE="$candidate"
      break
    fi
  done
fi
if [[ -n "$HELPER_EXE" ]]; then
  if [[ ! -f "$HELPER_EXE" ]]; then
    echo "ERROR: WeChat helper not found: $HELPER_EXE" >&2
    exit 1
  fi
  HELPER_ARGS=(--helper-exe "$HELPER_EXE")
elif [[ "${YDTV_ALLOW_MISSING_HELPER:-}" == "1" ]]; then
  echo "WARNING: building an incomplete package without 客户微信登录助手.exe" >&2
  HELPER_ARGS=(--allow-missing-helper)
else
  echo "ERROR: Windows WeChat helper (客户微信登录助手.exe) is required." >&2
  echo "Build it with build_wechat_windows.ps1 and copy it to downloads/, or set YDTV_WECHAT_HELPER_EXE=/path/to/exe." >&2
  echo "Set YDTV_ALLOW_MISSING_HELPER=1 only for local testing packages." >&2
  exit 1
fi

.venv/bin/python build/package_release.py \
  --dist dist/ydtv-signin \
  --output release \
  --platform linux \
  "${HELPER_ARGS[@]}"
printf 'Release package created in %s/release\n' "$ROOT"

