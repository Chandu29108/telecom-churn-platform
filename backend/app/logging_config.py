"""
Structured-enough logging for a single-process API: consistent format,
one place to change it. Not JSON-structured (no log aggregator in this
deployment yet) — swap the `format` string for a JSON formatter if/when
this ships behind something like Datadog or CloudWatch.
"""
import logging
import sys

from .config import ENVIRONMENT


def configure_logging() -> None:
    level = logging.INFO if ENVIRONMENT == "production" else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # Quiet down noisy third-party loggers so our own log lines aren't buried.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
