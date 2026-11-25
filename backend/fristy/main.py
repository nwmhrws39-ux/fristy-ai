"""Backend entry point: ``python -m fristy.main`` (launched by the desktop app)."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys


def main() -> None:
    from .config import RuntimeConfig

    config = RuntimeConfig.from_env()
    config.ensure_dirs()
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        config.data_dir / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=os.environ.get("FRISTY_LOG", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    if not os.environ.get("FRISTY_TOKEN"):
        logging.warning("FRISTY_TOKEN not set; generated a random token (dev mode). Token: %s", config.token)

    import uvicorn

    from .api.app import create_app

    app = create_app(config)
    # Loopback only. Never expose the control API on the network.
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="warning", access_log=False, ws_ping_interval=20)


if __name__ == "__main__":
    main()
