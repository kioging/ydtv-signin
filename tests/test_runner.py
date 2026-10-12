import json
import threading
import time

from app.accounts import Account
from app.db import connect, migrate
from app.runner import SigninRunner
from app.ydtv import ApiResponse


class StubClient:
    def __init__(self):
        self.calls = []
        self.signed = False

    def verify_token(self, token, space):
        return ApiResponse(200, {"code": 200, "data": {}})

    def get_signin_status(self, token, space):
        self.calls.append("status")
        return ApiResponse(200, {"code": 200, "data": {"今日已签": self.signed}})

    def sign(self, token, space):
        self.calls.append("sign")
        self.signed = True
        return ApiResponse(200, {"code": 200, "data": {"奖励金额": 1.5}, "msg": "ok"})

    def get_balance(self, token, space):
        self.calls.append("balance")
        return ApiResponse(200, {"code": 200, "data": {"余额": 20.5}})


def test_success_flow(tmp_path):
    migrate(tmp_path / "db.sqlite")
    client = StubClient()
    runner = SigninRunner(tmp_path / "db.sqlite", client)
    account = Account(id="a", label="A", token="secret")
    result = runner.run([account], "trigger")[0]
    assert result.status == "success"
    assert result.reward == 1.5
    assert result.balance == 20.5
    assert client.calls == ["status", "sign", "balance"]


def test_already_signed_skips_sign(tmp_path):
    migrate(tmp_path / "db.sqlite")

    class AlreadyClient(StubClient):
        def get_signin_status(self, token, space):
            return ApiResponse(200, {"code": 200, "data": {"今日已签": True}})

    runner = SigninRunner(tmp_path / "db.sqlite", AlreadyClient())
    result = runner.run([Account(id="a", label="A", token="secret")], "trigger")[0]
    assert result.status == "already_signed"


def test_second_run_preserves_existing_reward(tmp_path):
    migrate(tmp_path / "db.sqlite")
    client = StubClient()
    runner = SigninRunner(tmp_path / "db.sqlite", client)
    account = Account(id="a", label="A", token="secret")
    runner.run_account(account, "first")
    client.calls.clear()
    client.signed = True
    runner.run_account(account, "second")
    with connect(tmp_path / "db.sqlite") as connection:
        reward = connection.execute("SELECT reward FROM signins WHERE account_id = 'a'").fetchone()["reward"]
    assert reward == 1.5


def test_balance_failure_does_not_change_sign_success(tmp_path):
    migrate(tmp_path / "db.sqlite")

    class BalanceFailClient(StubClient):
        def get_balance(self, token, space):
            raise RuntimeError("balance timeout")

    runner = SigninRunner(tmp_path / "db.sqlite", BalanceFailClient())
    result = runner.run_account(Account(id="a", label="A", token="secret"), "trigger")
    assert result.status == "success"
    assert result.balance is None
    with connect(tmp_path / "db.sqlite") as connection:
        run_status = connection.execute("SELECT status FROM runs ORDER BY id DESC LIMIT 1").fetchone()["status"]
    assert run_status == "success"


def test_max_concurrency_runs_accounts_in_parallel(tmp_path):
    migrate(tmp_path / "db.sqlite")
    lock = threading.Lock()
    active = 0
    peak = 0

    class SlowClient(StubClient):
        def verify_token(self, token, space):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return ApiResponse(200, {"code": 200, "data": {}})

    runner = SigninRunner(tmp_path / "db.sqlite", SlowClient())
    accounts = [Account(id="a", label="A", token="a"), Account(id="b", label="B", token="b")]
    results = runner.run(accounts, "trigger", max_concurrency=2)
    assert len(results) == 2
    assert peak == 2

