import json

from app.config import (
    create_default_config,
    hash_password,
    load_config,
    set_web_password,
    update_scheduler_settings,
)
from app.accounts import Account, load_accounts, save_accounts


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

