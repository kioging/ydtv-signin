$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --specpath build\wechat-helper `
    --name ydtv-wechat-login `
    tools\ydtv_wechat_login.py

$stage = Join-Path $root "release\ydtv-wechat-login-windows"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item "dist\ydtv-wechat-login.exe" $stage
$readme = @(
    "ydtv.ai WeChat Login Helper",
    "",
    "1. Run ydtv-wechat-login.exe",
    "2. Click Start WeChat Login",
    "3. Complete WeChat login in the browser window",
    "4. The full callback URL will be copied to the clipboard automatically",
    "5. Paste it into Web Panel -> Add Account -> WeChat Login"
) -join [Environment]::NewLine
$readme | Set-Content -Encoding UTF8 (Join-Path $stage "README.txt")

$archive = Join-Path $root "release\ydtv-wechat-login-windows-x64.zip"
if (Test-Path $archive) { Remove-Item -Force $archive }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive
Write-Host "WeChat login helper created: $archive"
