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
.venv/bin/python build/package_release.py --dist dist/ydtv-signin --output release --platform linux
printf 'Release package created in %s/release\n' "$ROOT"

