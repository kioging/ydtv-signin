from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
import uuid
from pathlib import Path

from .accounts import Account, load_accounts, save_accounts
from .auth_flow import AuthFlowManager
from .config import hash_password, load_config, set_web_password
from .db import migrate
from .ydtv import YdtvClient


def _root_dir(path: str | None) -> Path:
    if path:
        return Path(path).resolve()
    environment_root = os.environ.get("YDTV_DATA_DIR")
    if environment_root:
        return Path(environment_root).resolve()
    return Path.cwd()


def _set_password(args: argparse.Namespace) -> int:
    root = _root_dir(args.root)
    config = load_config(root / "config.json")
    password = getpass.getpass("Web panel password: ")
    set_web_password(config, hash_password(password))
    print("Password hash saved.")
    return 0


def _account_add(args: argparse.Namespace) -> int:
    root = _root_dir(args.root)
    path = root / "accounts.json"
    accounts = load_accounts(path)
    account_id = args.account_id or f"account-{len(accounts) + 1}"
    if any(account.id == account_id for account in accounts):
        print(f"Account id already exists: {account_id}", file=sys.stderr)
        return 1
    token = getpass.getpass("ydtv.ai token (from browser localStorage): ").strip()
    if not token:
        print("Token cannot be empty.", file=sys.stderr)
        return 1
    label = input("Display label [optional]: ").strip() or account_id
    accounts.append(Account(id=account_id, label=label, token=token))
    save_accounts(path, accounts)
    print("Account saved.")
    return 0


def _account_test(args: argparse.Namespace) -> int:
    root = _root_dir(args.root)
    config = load_config(root / "config.json")
    accounts = load_accounts(root / "accounts.json")
    if not accounts:
        print("No accounts configured.", file=sys.stderr)
        return 1
    client = YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language)
    failures = 0
    for account in accounts:
        response = client.verify_token(account.token, account.space)
        valid = response.status_code == 200 and response.payload.get("code") in (None, 200)
        print(f"{account.id}: {'valid' if valid else 'invalid'}")
        if not valid:
            failures += 1
    return 1 if failures else 0


def _account_authorize(args: argparse.Namespace) -> int:
    root = _root_dir(args.root)
    config = load_config(root / "config.json")
    accounts_path = root / "accounts.json"
    account_id = args.account_id or f"account-{uuid.uuid4().hex[:8]}"
    existing = next((account for account in load_accounts(accounts_path) if account.id == account_id), None)
    label = existing.label if existing else account_id
    manager = AuthFlowManager(
        accounts_path,
        root / ".auth-profile",
        YdtvClient(config.site.base_url, config.site.api_prefix, config.site.language),
    )
    flow_id = manager.start(account_id, label, f"{config.site.base_url}/home")
    last_message = ""
    while True:
        status = manager.status(flow_id)
        if status is None:
            print("Authorization flow disappeared.", file=sys.stderr)
            return 1
        if status.message != last_message:
            print(status.message)
            last_message = status.message
        if status.state == "success":
            return 0
        if status.state in {"failed", "timeout"}:
            print(status.message, file=sys.stderr)
            return 1
        time.sleep(1)


def _browser_install(args: argparse.Namespace) -> int:
    from playwright.__main__ import main as playwright_main

    sys.argv = ["playwright", "install", "chromium"]
    try:
        playwright_main()
    except SystemExit as error:
        return int(error.code or 0)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ydtv.ai sign-in service CLI")
    parser.add_argument("--root", help="Application data directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("set-password")
    account = commands.add_parser("account")
    account_sub = account.add_subparsers(dest="account_command", required=True)
    add = account_sub.add_parser("add")
    add.add_argument("account_id", nargs="?")
    account_sub.add_parser("test")
    authorize = account_sub.add_parser("authorize")
    authorize.add_argument("account_id", nargs="?")
    browser = commands.add_parser("browser")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    browser_sub.add_parser("install")
    args = parser.parse_args(argv)

    root = _root_dir(args.root)
    migrate(root / "data" / "signin.db")

    if args.command == "set-password":
        return _set_password(args)
    if args.command == "account" and args.account_command == "add":
        return _account_add(args)
    if args.command == "account" and args.account_command == "test":
        return _account_test(args)
    if args.command == "account" and args.account_command == "authorize":
        return _account_authorize(args)
    if args.command == "browser" and args.browser_command == "install":
        return _browser_install(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

