import logging
import os


def configure_logging() -> None:
    """Console logging; LOG_LEVEL env var overrides. Chatty HTTP libraries are held at WARNING."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
