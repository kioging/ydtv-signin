$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt

$browserPath = $env:PLAYWRIGHT_BROWSERS_PATH
if (-not $browserPath) {
    $browserPath = Join-Path $env:LOCALAPPDATA "ms-playwright"
}
if (-not (Test-Path $browserPath)) {
    $env:PLAYWRIGHT_BROWSERS_PATH = $browserPath
    .\.venv\Scripts\python.exe -m playwright install chromium
}

$env:YDTV_BUNDLE_BROWSERS = $browserPath
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ydtv-signin.spec

if (-not (Test-Path "release")) { New-Item -ItemType Directory release | Out-Null }
.\.venv\Scripts\python.exe build\package_release.py --dist dist\ydtv-signin --output release --platform windows
Write-Host "Release package created in .\release"

