from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import atomic_write_json


ACCOUNTS_LOCK = threading.RLock()


@dataclass(frozen=True)
class Account:
    id: str
    label: str
    token: str
    enabled: bool = True
    space: str = "geren"
    avatar_url: str = ""
    user_id: str = ""
    token_expires_at: str = ""


def load_accounts(path: Path) -> list[Account]:
    with ACCOUNTS_LOCK:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        accounts: list[Account] = []
        seen: set[str] = set()
        for index, item in enumerate(raw.get("accounts", [])):
            account_id = str(item.get("id", "")).strip()
            token = str(item.get("token", "")).strip()
            if not account_id or not token:
                raise ValueError(f"accounts.json item {index} requires id and token")
            if account_id in seen:
                raise ValueError(f"Duplicate account id: {account_id}")
            seen.add(account_id)
            accounts.append(
                Account(
                    id=account_id,
                    label=str(item.get("label") or account_id),
                    token=token,
                    enabled=bool(item.get("enabled", True)),
                    space=str(item.get("space") or "geren"),
                    avatar_url=str(item.get("avatar_url") or ""),
                    user_id=str(item.get("user_id") or ""),
                    token_expires_at=str(item.get("token_expires_at") or ""),
                )
            )
        return accounts


def save_accounts(path: Path, accounts: list[Account]) -> None:
    with ACCOUNTS_LOCK:
        payload: dict[str, Any] = {
            "accounts": [
                {
                    "id": account.id,
                    "label": account.label,
                    "token": account.token,
                    "enabled": account.enabled,
                    "space": account.space,
                    "avatar_url": account.avatar_url,
                    "user_id": account.user_id,
                    "token_expires_at": account.token_expires_at,
                }
                for account in accounts
            ]
        }
        atomic_write_json(path, payload, private=True)


def remove_account(path: Path, account_id: str) -> bool:
    with ACCOUNTS_LOCK:
        accounts = load_accounts(path)
        remaining = [account for account in accounts if account.id != account_id]
        if len(remaining) == len(accounts):
            return False
        save_accounts(path, remaining)
        return True
