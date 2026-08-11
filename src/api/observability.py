"""Small structured-logging helpers that never receive request payloads."""

import json
import logging
from typing import Any


LOGGER = logging.getLogger("uvicorn.error")


def configure_logging(level: str) -> None:
    LOGGER.setLevel(level)


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    LOGGER.log(level, json.dumps(payload, separators=(",", ":"), default=str))
