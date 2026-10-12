import builtins
import getpass
import sqlite3

from app import cli
from app.accounts import load_accounts
from app.db import is_account_deleted, mark_account_deleted, migrate


def test_account_add_clears_deleted_tombstone(tmp_path, monkeypatch):
    migrate(tmp_path / "data" / "signin.db")
    mark_account_deleted(tmp_path / "data" / "signin.db", "main")
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "token-from-browser")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "Horcus")

    code = cli._account_add(type("Args", (), {"root": str(tmp_path), "account_id": "main"})())

    assert code == 0
    assert [account.id for account in load_accounts(tmp_path / "accounts.json")] == ["main"]
    assert is_account_deleted(tmp_path / "data" / "signin.db", "main") is False


def test_account_add_reports_tombstone_cleanup_failure(tmp_path, monkeypatch, capsys):
    migrate(tmp_path / "data" / "signin.db")
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "token-from-browser")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "Horcus")

    def fail_clear(path, account_id):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cli, "clear_account_tombstone", fail_clear)
    code = cli._account_add(type("Args", (), {"root": str(tmp_path), "account_id": "main"})())
    output = capsys.readouterr()

    assert code == 2
    assert "could not clear its deleted-account marker" in output.err
    assert [account.id for account in load_accounts(tmp_path / "accounts.json")] == ["main"]
