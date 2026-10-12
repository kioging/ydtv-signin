$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root ".venv\Scripts\python.exe") -m uvicorn app.main:app --host 0.0.0.0 --port 8848

