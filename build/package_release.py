from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


DEPLOY_README = """\
ydtv.ai automatic sign-in service

1. Set the Web password:
   Windows: ydtv-signin.exe set-password
   Linux:   ./ydtv-signin set-password

2. Add an account:
   Windows: ydtv-signin.exe account authorize
   Linux:   ./ydtv-signin account authorize

3. Start the service:
   Windows: start.bat
   Linux:   ./start.sh

The service listens on 0.0.0.0:8848 by default.
Configuration, account tokens, logs and data are stored beside the executable.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", required=True, choices=["windows", "linux"])
    args = parser.parse_args()

    dist = Path(args.dist).resolve()
    output = Path(args.output).resolve()
    if not (dist / "ydtv-signin").exists() and not (dist / "ydtv-signin.exe").exists():
        raise FileNotFoundError(f"Build output not found: {dist}")

    stage = output / f"ydtv-signin-{args.platform}"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(dist, stage)
    (stage / "data").mkdir(exist_ok=True)
    (stage / "logs").mkdir(exist_ok=True)
    (stage / "accounts.json").write_text('{\n  "accounts": []\n}\n', encoding="utf-8")
    (stage / "README-DEPLOY.txt").write_text(DEPLOY_README, encoding="utf-8")

    if args.platform == "windows":
        (stage / "start.bat").write_text(
            '@echo off\r\ncd /d "%~dp0"\r\nydtv-signin.exe\r\n',
            encoding="utf-8",
        )
    else:
        start_script = stage / "start.sh"
        start_script.write_text(
            '#!/usr/bin/env sh\ncd "$(dirname "$0")"\nexec ./ydtv-signin\n',
            encoding="utf-8",
        )
        start_script.chmod(0o755)
        binary = stage / "ydtv-signin"
        if binary.exists():
            binary.chmod(0o755)

    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"ydtv-signin-{args.platform}-x64.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for path in stage.rglob("*"):
            if path.is_file():
                handle.write(path, path.relative_to(stage.parent))
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

