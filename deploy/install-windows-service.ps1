$ErrorActionPreference = "Stop"

$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm) {
    throw "NSSM is required. Install NSSM and ensure nssm.exe is in PATH."
}

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run py -3.11 -m venv .venv and install requirements first."
}

& nssm install YdtvSignin $python "-m uvicorn app.main:app --host 0.0.0.0 --port 8848"
& nssm set YdtvSignin AppDirectory $root
& nssm set YdtvSignin AppStdout (Join-Path $root "logs\service.log")
& nssm set YdtvSignin AppStderr (Join-Path $root "logs\service-error.log")
& nssm set YdtvSignin Start SERVICE_AUTO_START
& nssm start YdtvSignin

