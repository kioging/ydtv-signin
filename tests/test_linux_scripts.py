from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "deploy" / "linux"


def test_systemd_unit_template_has_no_quoted_paths():
    """systemd 的 WorkingDirectory= 等指令不接受引号包裹路径，加了会报 bad unit file setting。"""
    text = (SCRIPTS_DIR / "install-service.sh").read_text(encoding="utf-8")
    assert "WorkingDirectory=" in text
    assert 'WorkingDirectory="' not in text
    assert 'Environment="' not in text
    assert 'ExecStart="' not in text


def test_systemd_unit_template_keeps_required_directives():
    text = (SCRIPTS_DIR / "install-service.sh").read_text(encoding="utf-8")
    for directive in (
        "Type=simple",
        "Restart=always",
        "RestartSec=5",
        "WantedBy=multi-user.target",
        "systemctl daemon-reload",
        "systemctl enable",
        "systemctl is-active",
    ):
        assert directive in text


def test_linux_deploy_scripts_use_lf_and_bash_shebang():
    scripts = sorted(SCRIPTS_DIR.glob("*.sh"))
    assert scripts, "no deploy/linux scripts found"
    for script in scripts:
        data = script.read_bytes()
        assert b"\r" not in data, f"{script.name} contains CRLF line endings"
        assert data.startswith(b"#!/usr/bin/env bash"), f"{script.name} has an unexpected shebang"
