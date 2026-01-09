"""Utility functions for field normalization."""

from __future__ import annotations

import re
from typing import Optional

from slugify import slugify

WHITESPACE_RE = re.compile(r"\s+")


def normalize_string(value: str | None) -> Optional[str]:
    """Trim and collapse whitespace, returning None for empty values."""
    if value is None:
        return None
    normalized = WHITESPACE_RE.sub(" ", value).strip()
    return normalized or None


def normalize_artist_name(value: str | None) -> Optional[str]:
    """Normalize artist names while preserving case for word separation."""
    normalized = normalize_string(value)
    if normalized is None:
        return None
    return normalized.replace("Feat.", "feat.").replace("Featuring", "feat.")


def normalize_duration_ms(duration_ms: int | float | None) -> Optional[int]:
    """Ensure duration is an integer number of milliseconds."""
    if duration_ms is None:
        return None
    return int(duration_ms)


def slugify_value(value: str) -> str:
    """Produce a slug for deduplication keys."""
    return slugify(value or "", lowercase=True, separator="-")
