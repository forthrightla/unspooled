"""MusicBrainz enrichment client and cache helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from playback_analytics.config import Settings


@dataclass(slots=True)
class MusicBrainzResponse:
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    fetched_at: datetime


class MusicBrainzClient:
    """Thin wrapper around MusicBrainz HTTP API with caching hooks."""

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        mb_settings = settings.enrichment.musicbrainz
        self.user_agent = mb_settings.app_name
        self.rate_limit = mb_settings.rate_limit_per_second
        self.last_request_time: float = 0.0
        self.http = httpx.Client(
            timeout=20,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )

    def _respect_rate_limit(self) -> None:
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        elapsed = time.perf_counter() - self.last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def fetch(
        self,
        entity: str,
        mbid: str,
        params: dict[str, str] | None = None,
    ) -> MusicBrainzResponse:
        """Fetch an entity by MBID."""
        self._respect_rate_limit()
        response = self.http.get(f"{self.BASE_URL}/{entity}/{mbid}", params=params)
        response.raise_for_status()
        self.last_request_time = time.perf_counter()
        return MusicBrainzResponse(
            entity_type=entity,
            entity_id=mbid,
            payload=response.json(),
            fetched_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def to_cache_row(resp: MusicBrainzResponse) -> tuple[str, str, str, str]:
        """Convert response to SQLite row tuple."""
        return (
            resp.entity_type,
            resp.entity_id,
            json.dumps(resp.payload),
            resp.fetched_at.isoformat(),
        )
