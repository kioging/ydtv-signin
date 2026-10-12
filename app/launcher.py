from __future__ import annotations

import os
import sys
from pathlib import Path

from app.config import AppConfig, load_config


def _data_root() -> Path:
    configured = os.environ.get("YDTV_DATA_DIR")
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _ssl_options(config: AppConfig, data_root: Path) -> dict[str, str]:
    """Return uvicorn TLS options; empty means plain HTTP."""
    if not (config.web.tls_certfile and config.web.tls_keyfile):
        return {}
    options: dict[str, str] = {}
    for key, value in (
        ("ssl_certfile", config.web.tls_certfile),
        ("ssl_keyfile", config.web.tls_keyfile),
    ):
        path = Path(value)
        options[key] = str(path if path.is_absolute() else (data_root / path).resolve())
    return options


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    data_root = _data_root()
    os.environ.setdefault("YDTV_DATA_DIR", str(data_root))
    if arguments and arguments[0] in {"set-password", "account"}:
        from app.cli import main as cli_main

        return cli_main(arguments)

    import uvicorn

    from app.main import app

    config = load_config(data_root / "config.json")
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level=config.logging.level.lower(),
        workers=1,
        **_ssl_options(config, data_root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
