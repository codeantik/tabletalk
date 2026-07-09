"""Structured-ish logging: one line per event, key=value fields.

Not a JSON/structlog setup -- for a PoC, greppable `event key=val key=val`
lines on stdout are enough to satisfy the "structured logging, not print
statements" requirement (question/SQL/validation/execution/latency per
query) without adding a logging dependency.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    rendered = " ".join(f"{key}={value!r}" for key, value in fields.items())
    logger.info("%s %s", event, rendered)
