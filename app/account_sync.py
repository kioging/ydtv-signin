from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass

from .accounts import ACCOUNTS_LOCK, Account, load_accounts, save_accounts
from .db import transaction
from .ydtv import YdtvClient


@dataclass
class SyncResult:
    account_id: str
    label: str
    avatar_url: str
    balance: float | None
    created: bool
    token_expires_at: str = ""
    token: str = ""
    user_id: str = ""


def sync_account(
    accounts_path: Path,
    database_path: Path,
    account_id: str,
    client: YdtvClient,
    token: str,
    verification_payload: dict | None = None,
) -> SyncResult:
    response = client.get_user_info(token)
    if response.status_code != 200 or response.payload.get("code") not in (None, 200):
        raise RuntimeError(str(response.payload.get("msg") or "User information query failed"))
    data = response.payload.get("data") or {}
    user_id = str(data.get("id") or "")
    label = str(data.get("昵称") or data.get("nickname") or account_id)
    avatar_url = str(data.get("头像") or "")
    raw_balance = data.get("余额")
    try:
        balance = float(raw_balance) if raw_balance is not None else None
    except (TypeError, ValueError):
        balance = None

    if verification_payload is None:
        verification = client.verify_token(token)
        if verification.status_code != 200 or verification.payload.get("code") not in (None, 200):
            raise RuntimeError(str(verification.payload.get("msg") or "Token verification failed"))
        verification_data = verification.payload.get("data") or {}
    else:
        verification_data = verification_payload.get("data") or {}
    token_expires_at = str(verification_data.get("过期时间") or "")
    rotated_token = str(verification_data.get("token") or token)

    with ACCOUNTS_LOCK:
        accounts = load_accounts(accounts_path)
        target_index = next(
            (
                index
                for index, account in enumerate(accounts)
                if (user_id and account.user_id == user_id)
                or account.token == token
                or account.id == account_id
            ),
            None,
        )
        created = target_index is None
        if target_index is None:
            target_id = account_id
            accounts.append(
                Account(
                    id=account_id,
                    label=label,
                    token=rotated_token,
                    avatar_url=avatar_url,
                    user_id=user_id,
                    token_expires_at=token_expires_at,
                )
            )
        else:
            account = accounts[target_index]
            target_id = account.id
            accounts[target_index] = Account(
                id=account.id,
                label=label,
                token=rotated_token,
                enabled=account.enabled,
                space=account.space,
                avatar_url=avatar_url,
                user_id=user_id,
                token_expires_at=token_expires_at,
            )

        unique_accounts: list[Account] = []
        seen_identities: set[str] = set()
        for account in accounts:
            identity = f"user:{account.user_id}" if account.user_id else f"token:{account.token}"
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            unique_accounts.append(account)
        save_accounts(accounts_path, unique_accounts)

    with transaction(database_path) as connection:
        timestamp = connection.execute("SELECT datetime('now') || 'Z' AS value").fetchone()["value"]
        connection.execute(
            """
            INSERT INTO accounts(account_id, label, avatar_url, user_id, token_expires_at, balance, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
              label=excluded.label,
              avatar_url=excluded.avatar_url,
              user_id=excluded.user_id,
              token_expires_at=excluded.token_expires_at,
              balance=excluded.balance,
              updated_at=excluded.updated_at
            """,
            (target_id, label, avatar_url, user_id, token_expires_at, balance, timestamp),
        )
    return SyncResult(target_id, label, avatar_url, balance, created, token_expires_at, rotated_token, user_id)
