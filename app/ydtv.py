from __future__ import annotations

import base64
import random
import string
from dataclasses import dataclass
from typing import Any

import httpx



def _derive_mask_key() -> bytes:
    # Reproduces the browser's obfuscated key derivation. Kept isolated so a
    # future site update only requires changes in this module.
    seed = 137
    values = [188, 125, 42, 166, 175, 21, 53, 39, 111, 122, 214, 134, 92, 108, 3, 33, 63, 102, 67, 255, 152, 119, 164, 104, 166, 113, 195, 231, 106, 99, 61, 121]
    result = bytearray()
    for value in values:
        result.append(value ^ seed)
        seed = (seed * 17 + 23) & 255
    return bytes(result)


def encode_token(token: str) -> str:
    """Apply the current ydtv.ai front-end token header transformation."""
    lowercase = string.ascii_lowercase
    mixed = string.ascii_letters
    alphanumeric = string.ascii_lowercase + string.digits
    mixed_alphanumeric = string.ascii_letters + string.digits
    prefix = (
        "".join(random.choice(lowercase) for _ in range(5))
        + "."
        + "".join(random.choice(string.digits) for _ in range(3))
        + "@"
        + "".join(random.choice(mixed) for _ in range(6))
        + "-"
        + "".join(random.choice(alphanumeric) for _ in range(4))
        + "="
        + "".join(random.choice(mixed_alphanumeric) for _ in range(6))
    )
    raw = (prefix + "|" + token).encode("utf-8")
    transformed = bytes((byte + 7) & 255 for byte in raw)
    key = _derive_mask_key()
    masked = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(transformed))
    return base64.b64encode(masked[::-1]).decode("ascii")


@dataclass
class ApiResponse:
    status_code: int
    payload: dict[str, Any]


class YdtvClient:
    def __init__(
        self,
        base_url: str = "https://ydtv.ai",
        api_prefix: str = "/houduan",
        language: str = "zh",
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_prefix = api_prefix.rstrip("/")
        self._language = language
        self._transport = transport
        self._timeout = timeout

    def _headers(self, token: str, space: str = "geren") -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept-Language": self._language,
            "x-kongjian": space,
            "token": encode_token(token),
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{self._api_prefix}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        space: str = "geren",
        json_body: dict[str, Any] | None = None,
    ) -> ApiResponse:
        with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
            response = client.request(
                method,
                self._url(path),
                headers=self._headers(token, space),
                json=json_body if json_body is not None else None,
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"code": -1, "msg": "Non-JSON response", "raw": response.text[:500]}
        if not isinstance(payload, dict):
            payload = {"code": -1, "msg": "Unexpected response", "data": payload}
        return ApiResponse(response.status_code, payload)

    def verify_token(self, token: str, space: str = "geren") -> ApiResponse:
        return self._request("POST", "/user/tokenyanzheng", token=token, space=space, json_body={})

    def get_user_info(self, token: str, space: str = "geren") -> ApiResponse:
        return self._request("POST", "/user/chaxunyonghuxinxi", token=token, space=space, json_body={})

    def get_signin_status(self, token: str, space: str = "geren") -> ApiResponse:
        return self._request("GET", "/marketing/qiandao/zhuangtai", token=token, space=space)

    def sign(self, token: str, space: str = "geren") -> ApiResponse:
        return self._request("POST", "/marketing/qiandao", token=token, space=space, json_body={})

    def get_balance(self, token: str, space: str = "geren") -> ApiResponse:
        return self._request("POST", "/user/chaxunyue", token=token, space=space, json_body={})

