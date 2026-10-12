$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt

powershell -ExecutionPolicy Bypass -File .\build\build_wechat_windows.ps1
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ydtv-signin.spec

if (-not (Test-Path "release")) { New-Item -ItemType Directory release | Out-Null }
.\.venv\Scripts\python.exe build\package_release.py `
    --dist dist\ydtv-signin `
    --output release `
    --platform windows `
    --helper-exe dist\ydtv-wechat-login.exe
Write-Host "Release package created in .\release"

