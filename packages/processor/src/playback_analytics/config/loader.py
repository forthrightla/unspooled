"""Settings loader using TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .models import Settings


def load_settings(path: str | Path) -> Settings:
    """Load Settings from a TOML file path."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    return Settings(**data)
