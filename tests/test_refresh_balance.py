import asyncio
import json

import pytest
from fastapi import HTTPException

from app.account_sync import AccountNotFoundError, SyncResult
from app.accounts import Account, save_accounts
from app.auth import csrf_token
from app.db import migrate


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setenv("YDTV_DATA_DIR", str(tmp_path))
    import app.main as main

    monkeypatch.setattr(main, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "signin.db")
    migrate(tmp_path / "signin.db")
    save_accounts(tmp_path / "accounts.json", [Account(id="a", label="A", token="token-a")])
    return main


def test_refresh_balance_does_not_recreate_deleted_account(tmp_path, monkeypatch):
    main = _prepare(tmp_path, monkeypatch)
    captured = {}

    def fake_sync(*args, **kwargs):
        captured.update(kwargs)
        raise AccountNotFoundError("Account a was removed")

    monkeypatch.setattr(main, "sync_account", fake_sync)
    token = csrf_token(main.config.web.session_secret)

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.refresh_balance(account_id="a", csrf_header=token, _=None))

    assert error.value.status_code == 404
    assert captured.get("allow_create") is False


def test_refresh_balance_returns_updated_balance(tmp_path, monkeypatch):
    main = _prepare(tmp_path, monkeypatch)

    def fake_sync(*args, **kwargs):
        return SyncResult(
            account_id="a",
            label="Horcus",
            avatar_url="",
            balance=12.5,
            created=False,
            token_expires_at="2026-11-11 23:11:41",
        )

    monkeypatch.setattr(main, "sync_account", fake_sync)
    token = csrf_token(main.config.web.session_secret)

    response = asyncio.run(main.refresh_balance(account_id="a", csrf_header=token, _=None))
    payload = json.loads(response.body)

    assert payload["balance"] == 12.5
    assert payload["name"] == "Horcus"
