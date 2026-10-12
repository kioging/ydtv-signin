from __future__ import annotations

import os
import sys
from pathlib import Path


def _data_root() -> Path:
    configured = os.environ.get("YDTV_DATA_DIR")
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    data_root = _data_root()
    os.environ.setdefault("YDTV_DATA_DIR", str(data_root))
    if getattr(sys, "frozen", False):
        resource_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for candidate in (resource_root / "ms-playwright", Path(sys.executable).parent / "ms-playwright"):
            if candidate.exists():
                os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(candidate))
                break

    if arguments and arguments[0] in {"set-password", "account", "browser"}:
        from app.cli import main as cli_main

        return cli_main(arguments)

    import uvicorn

    from app.config import load_config
    from app.main import app

    config = load_config(data_root / "config.json")
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level=config.logging.level.lower(),
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
