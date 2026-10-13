import os
import subprocess
import sys
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "build" / "package_release.py"
HELPER_NAME = "客户微信登录助手.exe"


def _fake_dist(root: Path) -> Path:
    dist = root / "dist" / "ydtv-signin"
    dist.mkdir(parents=True)
    (dist / "ydtv-signin").write_bytes(b"binary")
    return dist


def _run_package(dist: Path, output: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dist",
            str(dist),
            "--output",
            str(output),
            "--platform",
            "linux",
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_linux_package_includes_wechat_helper(tmp_path):
    dist = _fake_dist(tmp_path)
    helper = tmp_path / "ydtv-wechat-login.exe"
    helper.write_bytes(b"MZ" + b"\x00" * 64)
    output = tmp_path / "release"

    result = _run_package(dist, output, "--helper-exe", str(helper))

    assert result.returncode == 0, result.stderr
    archive = output / "ydtv-signin-linux-x64.zip"
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
        assert f"ydtv-signin-linux/downloads/{HELPER_NAME}" in names
        for script in ("start.sh", "stop.sh", "restart.sh", "install-service.sh", "uninstall-service.sh"):
            assert f"ydtv-signin-linux/{script}" in names
            if os.name == "posix":
                mode = handle.getinfo(f"ydtv-signin-linux/{script}").external_attr >> 16
                assert mode & 0o111, f"{script} should be executable in the zip"
        assert handle.read(f"ydtv-signin-linux/downloads/{HELPER_NAME}").startswith(b"MZ")


def test_package_requires_wechat_helper(tmp_path):
    dist = _fake_dist(tmp_path)
    output = tmp_path / "release"

    result = _run_package(dist, output)

    assert result.returncode != 0
    assert "--helper-exe is required" in (result.stderr + result.stdout)
