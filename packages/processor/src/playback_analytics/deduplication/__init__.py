"""Deduplication helpers for canonical entity creation."""

from .engine import DeduplicationEngine, DeduplicationStats
from .matcher import AliasMatcher, DeduplicationResult

__all__ = ["AliasMatcher", "DeduplicationResult", "DeduplicationEngine", "DeduplicationStats"]
