"""Unspooled Processor - Music Analytics Pipeline."""

from importlib import metadata


def get_version() -> str:
    """Return the installed package version."""
    try:
        return metadata.version("unspooled-processor")
    except metadata.PackageNotFoundError:  # pragma: no cover - during local dev
        return "0.0.0"


__all__ = ["get_version"]
