"""Ingestion connectors for external listening sources."""

from .apple_music import AppleMusicIngestor
from .lastfm import LastFMIngestor
from .spotify import SpotifyIngestor

__all__ = [
    "AppleMusicIngestor",
    "LastFMIngestor",
    "SpotifyIngestor",
]
