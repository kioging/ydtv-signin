import pytest

from app.account_sync import AccountNotFoundError, sync_account
from app.accounts import Account, load_accounts, save_accounts
from app.db import is_account_deleted, mark_account_deleted, migrate
from app.ydtv import ApiResponse


class StubClient:
    def __init__(self, user_id: str, label: str = "Horcus", token: str = "new-token"):
        self.user_id = user_id
        self.label = label
        self.token = token

    def get_user_info(self, token, space="geren"):
        return ApiResponse(
            200,
            {
                "code": 200,
                "data": {
                    "id": self.user_id,
                    "昵称": self.label,
                    "头像": "https://example.com/avatar.png",
                    "余额": 2.5,
                },
            },
        )

    def verify_token(self, token, space="geren"):
        return ApiResponse(
            200,
            {
                "code": 200,
                "data": {
                    "过期时间": "2026-11-11 13:31:14",
                },
            },
        )


def test_duplicate_user_updates_existing_account(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    database_path = tmp_path / "signin.db"
    migrate(database_path)
    save_accounts(
        accounts_path,
        [Account(id="main", label="Old", token="old-token", user_id="10931275")],
    )

    result = sync_account(
        accounts_path,
        database_path,
        "account-2",
        StubClient("10931275"),
        "new-token",
    )

    accounts = load_accounts(accounts_path)
    assert result.created is False
    assert result.account_id == "main"
    assert len(accounts) == 1
    assert accounts[0].token == "new-token"
    assert accounts[0].token_expires_at == "2026-11-11 13:31:14"


def test_new_user_is_added(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    database_path = tmp_path / "signin.db"
    migrate(database_path)
    save_accounts(
        accounts_path,
        [Account(id="main", label="Old", token="old-token", user_id="100")],
    )

    result = sync_account(
        accounts_path,
        database_path,
        "account-2",
        StubClient("200", label="Second", token="second-token"),
        "second-token",
    )

    assert result.created is True
    assert len(load_accounts(accounts_path)) == 2


def test_rotated_token_is_saved(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    database_path = tmp_path / "signin.db"
    migrate(database_path)
    save_accounts(accounts_path, [Account(id="main", label="Old", token="old-token", user_id="100")])

    class RotatingClient(StubClient):
        def verify_token(self, token, space="geren"):
            return ApiResponse(
                200,
                {
                    "code": 200,
                    "data": {
                        "过期时间": "2026-11-11 13:31:14",
                        "token": "rotated-token",
                    },
                },
            )

    result = sync_account(
        accounts_path,
        database_path,
        "main",
        RotatingClient("100"),
        "old-token",
    )
    assert result.token == "rotated-token"
    assert load_accounts(accounts_path)[0].token == "rotated-token"


def test_allow_create_false_does_not_resurrect_deleted_account(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    database_path = tmp_path / "signin.db"
    migrate(database_path)
    save_accounts(accounts_path, [])

    with pytest.raises(AccountNotFoundError):
        sync_account(
            accounts_path,
            database_path,
            "deleted-account",
            StubClient("100"),
            "token",
            allow_create=False,
        )
    assert load_accounts(accounts_path) == []


def test_readd_clears_deleted_account_tombstone(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    database_path = tmp_path / "signin.db"
    migrate(database_path)
    save_accounts(accounts_path, [])
    mark_account_deleted(database_path, "main")
    assert is_account_deleted(database_path, "main") is True

    sync_account(
        accounts_path,
        database_path,
        "main",
        StubClient("100"),
        "token",
    )

    assert is_account_deleted(database_path, "main") is False
    assert [account.id for account in load_accounts(accounts_path)] == ["main"]
