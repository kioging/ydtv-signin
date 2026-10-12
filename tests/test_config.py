import json

import pytest

from app.config import (
    create_default_config,
    hash_password,
    load_config,
    set_web_password,
    update_scheduler_settings,
)
from app.accounts import Account, load_accounts, remove_account, save_accounts
from app.launcher import _ssl_options


def test_default_config_created(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["scheduler"]["daily_time"] == "09:05"


def test_load_config_merges_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"site": {"base_url": "https://example.com"}}), encoding="utf-8")
    config = load_config(path, create=False)
    assert config.site.base_url == "https://example.com"
    assert config.scheduler.daily_time == "09:05"


def test_web_tls_config(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["web"]["tls_certfile"] = "/etc/ssl/panel.crt"
    raw["web"]["tls_keyfile"] = "/etc/ssl/panel.key"
    path.write_text(json.dumps(raw), encoding="utf-8")
    config = load_config(path, create=False)
    assert config.web.tls_certfile == "/etc/ssl/panel.crt"
    assert config.web.tls_keyfile == "/etc/ssl/panel.key"


def test_web_tls_requires_both_files(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["web"]["tls_certfile"] = "/etc/ssl/panel.crt"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path, create=False)


def test_ssl_options_disabled_by_default(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    config = load_config(path, create=False)
    assert _ssl_options(config, tmp_path) == {}


def test_ssl_options_resolve_relative_paths(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["web"]["tls_certfile"] = "certs/panel.crt"
    raw["web"]["tls_keyfile"] = "certs/panel.key"
    path.write_text(json.dumps(raw), encoding="utf-8")
    config = load_config(path, create=False)
    options = _ssl_options(config, tmp_path)
    assert options["ssl_certfile"] == str((tmp_path / "certs" / "panel.crt").resolve())
    assert options["ssl_keyfile"] == str((tmp_path / "certs" / "panel.key").resolve())


def test_password_hash_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    config = load_config(path)
    set_web_password(config, hash_password("a-strong-password-123"))
    config = load_config(path, create=False)
    assert config.web.password_hash.startswith("$argon2id$")


def test_account_avatar_roundtrip(tmp_path):
    path = tmp_path / "accounts.json"
    save_accounts(
        path,
        [
            Account(
                id="main",
                label="Horcus",
                token="secret",
                avatar_url="https://example.com/avatar.png",
                user_id="10931275",
            )
        ],
    )
    account = load_accounts(path)[0]
    assert account.avatar_url == "https://example.com/avatar.png"
    assert account.user_id == "10931275"


def test_update_scheduler_settings(tmp_path):
    path = tmp_path / "config.json"
    create_default_config(path)
    config = load_config(path)
    update_scheduler_settings(
        config,
        enabled=False,
        daily_time="08:30",
        jitter_seconds=(10, 20),
        retry_delay_minutes=15,
        max_retries=2,
        max_concurrency=1,
        keepalive_interval_hours=4,
    )
    updated = load_config(path, create=False)
    assert updated.scheduler.enabled is False
    assert updated.scheduler.daily_time == "08:30"
    assert updated.scheduler.keepalive_interval_hours == 4


def test_remove_account(tmp_path):
    path = tmp_path / "accounts.json"
    save_accounts(
        path,
        [
            Account(id="a", label="A", token="token-a"),
            Account(id="b", label="B", token="token-b"),
        ],
    )
    assert remove_account(path, "a") is True
    assert [account.id for account in load_accounts(path)] == ["b"]
    assert remove_account(path, "missing") is False

