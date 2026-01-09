"""Central logging configuration."""

from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import Any, Mapping

DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _base_config(level: str) -> Mapping[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": DEFAULT_FORMAT},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
            }
        },
        "root": {"handlers": ["console"], "level": level},
    }


def configure_logging(level: str = "INFO") -> None:
    """Configure logging with a consistent formatter."""
    dictConfig(_base_config(level))
    logging.getLogger(__name__).debug("Logging configured at %s", level)
