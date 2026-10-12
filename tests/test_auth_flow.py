from pathlib import Path

from app.auth_flow import AuthFlowManager


class StubClient:
    pass


def test_profile_path_is_isolated_per_account(tmp_path):
    manager = AuthFlowManager(
        accounts_path=tmp_path / "accounts.json",
        profile_path=tmp_path / ".auth-profile",
        client=StubClient(),
    )
    first = manager._profile_for("account-1")
    second = manager._profile_for("account-2")
    assert first == tmp_path / ".auth-profile" / "account-1"
    assert second == tmp_path / ".auth-profile" / "account-2"
    assert first != second


def test_profile_path_sanitizes_unsafe_characters(tmp_path):
    manager = AuthFlowManager(
        accounts_path=tmp_path / "accounts.json",
        profile_path=tmp_path / ".auth-profile",
        client=StubClient(),
    )
    assert manager._profile_for("../bad id").name == "___bad_id"
