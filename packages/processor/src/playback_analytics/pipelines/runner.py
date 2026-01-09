"""Top-level orchestration for the ingestion → normalization → persistence pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict

from playback_analytics.config import Settings
from playback_analytics.deduplication import AliasMatcher
from playback_analytics.ingestion import AppleMusicIngestor, LastFMIngestor, SpotifyIngestor
from playback_analytics.normalization import normalize_artist_name, normalize_string

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Lightweight structure to capture counts at each stage."""

    raw_spotify_events: int = 0
    raw_lastfm_events: int = 0
    raw_apple_music_events: int = 0
    normalized_events: int = 0

    extra: Dict[str, int] = field(default_factory=dict)


class PlaybackPipeline:
    """Coordinates ingestion, normalization, deduplication, and persistence."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.spotify = SpotifyIngestor(settings)
        self.lastfm = LastFMIngestor(settings)
        self.apple = AppleMusicIngestor(settings)
        self.matcher = AliasMatcher()

    def run(self) -> PipelineStats:
        """Execute one end-to-end synchronization pass."""
        stats = PipelineStats()
        logger.info("Starting playback pipeline for environment=%s", self.settings.metadata.environment)

        spotify_events = self.spotify.load_raw_events()
        stats.raw_spotify_events = len(spotify_events)
        logger.info("Loaded %s Spotify events", stats.raw_spotify_events)

        lastfm_events = self.lastfm.load_raw_scrobbles()
        stats.raw_lastfm_events = len(lastfm_events)
        logger.info("Loaded %s Last.fm scrobbles", stats.raw_lastfm_events)

        try:
            apple_events = self.apple.extract_play_history()
        except FileNotFoundError:
            apple_events = []
            logger.debug("Apple Music XML not configured; skipping parse.")
        stats.raw_apple_music_events = len(apple_events)

        normalized = self._normalize_events(spotify_events + lastfm_events + apple_events)
        stats.normalized_events = len(normalized)
        logger.info("Normalized %s events (placeholder implementation)", stats.normalized_events)

        # TODO: persist normalized events, run deduplication + enrichment, upsert into DB.
        logger.info("Pipeline run complete (data persistence not yet implemented).")
        return stats

    def _normalize_events(self, events: list[dict]) -> list[dict]:
        normalized_events: list[dict] = []
        for event in events:
            normalized_events.append(
                {
                    "track": normalize_string(event.get("trackName") or event.get("track_name")),
                    "artist": normalize_artist_name(
                        event.get("artistName") or event.get("master_metadata_artist_name")
                    ),
                }
            )
        return normalized_events
