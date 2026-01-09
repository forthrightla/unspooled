"""Typed configuration models for Unspooled Processor."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MetadataSettings(BaseModel):
    environment: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "UTC"


class PathSettings(BaseModel):
    # Primary input directory (new unified style)
    input_dir: Path | None = None
    # Legacy individual paths (kept for backward compatibility)
    raw_spotify_history: Path | None = None
    raw_lastfm_exports: Path | None = None
    raw_apple_music_exports: Path | None = None
    # Output paths
    database_path: Path
    musicbrainz_cache: Path
    export_output: Path | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path | None) -> Path | None:
        if value is None or value == "":
            return None
        return Path(value).expanduser().resolve()

    def get_spotify_path(self) -> Path:
        """Get Spotify input path, preferring input_dir if set."""
        if self.raw_spotify_history:
            return self.raw_spotify_history
        if self.input_dir:
            return self.input_dir
        raise ValueError("No Spotify input path configured")

    def get_lastfm_path(self) -> Path:
        """Get Last.fm input path, preferring input_dir if set."""
        if self.raw_lastfm_exports:
            return self.raw_lastfm_exports
        if self.input_dir:
            return self.input_dir
        raise ValueError("No Last.fm input path configured")

    def get_apple_music_path(self) -> Path:
        """Get Apple Music input path, preferring input_dir if set."""
        if self.raw_apple_music_exports:
            return self.raw_apple_music_exports
        if self.input_dir:
            return self.input_dir
        raise ValueError("No Apple Music input path configured")


class SpotifyIngestionSettings(BaseModel):
    history_glob: str = "Streaming_History*.json"
    min_duration_seconds: int = 30
    skip_podcasts: bool = True


class LastFMIngestionSettings(BaseModel):
    export_glob: str = "*.csv"
    dedupe_identical_scrobbles: bool = True


class AppleMusicSettings(BaseModel):
    library_xml_path: Optional[Path] = None
    token: str | None = None

    @field_validator("library_xml_path", mode="before")
    @classmethod
    def _expand_library(cls, value: str | Path | None) -> Path | None:
        if value in (None, ""):
            return None
        return Path(value).expanduser().resolve()


class MusicBrainzSettings(BaseModel):
    app_name: str = Field(
        default="playback-analytics/0.1 (contact@example.com)",
        description="Format: app-name/version (contact@example.com)",
    )
    rate_limit_per_second: float = 1.0


class IngestionSettings(BaseModel):
    spotify: SpotifyIngestionSettings = SpotifyIngestionSettings()
    lastfm: LastFMIngestionSettings = LastFMIngestionSettings()
    apple_music: AppleMusicSettings = AppleMusicSettings()


class EnrichmentSettings(BaseModel):
    enabled: bool = True
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    musicbrainz: MusicBrainzSettings = MusicBrainzSettings()


class Settings(BaseModel):
    metadata: MetadataSettings
    paths: PathSettings
    ingestion: IngestionSettings
    enrichment: EnrichmentSettings = EnrichmentSettings()
