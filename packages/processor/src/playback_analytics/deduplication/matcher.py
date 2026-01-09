"""Fuzzy matching helpers for deduplicating artists/albums/tracks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DeduplicationResult:
    canonical_id: int | None
    confidence: float
    method: str
    notes: str | None = None


class AliasMatcher:
    """Placeholder for sophisticated fuzzy matching logic."""

    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = threshold

    def match(self, normalized_value: str) -> DeduplicationResult:
        # Future implementation: use trigram similarity / embeddings.
        return DeduplicationResult(
            canonical_id=None,
            confidence=0.0,
            method="unmatched",
            notes=f"No match for '{normalized_value}'",
        )
