$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt

.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ydtv-signin.spec

if (-not (Test-Path "release")) { New-Item -ItemType Directory release | Out-Null }
.\.venv\Scripts\python.exe build\package_release.py --dist dist\ydtv-signin --output release --platform windows
Write-Host "Release package created in .\release"

