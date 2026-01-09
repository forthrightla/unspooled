"""Shared pytest fixtures for playback analytics tests."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List

import textwrap

import pytest

from playback_analytics.config.models import (
    AppleMusicSettings,
    EnrichmentSettings,
    IngestionSettings,
    LastFMIngestionSettings,
    MetadataSettings,
    PathSettings,
    Settings,
    SpotifyIngestionSettings,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def temp_settings(tmp_path: Path) -> Settings:
    """Build a fresh Settings object rooted at a temp directory."""
    raw_spotify = tmp_path / "spotify"
    raw_lastfm = tmp_path / "lastfm"
    raw_apple = tmp_path / "apple"
    for path in (raw_spotify, raw_lastfm, raw_apple):
        path.mkdir()

    ingestion = IngestionSettings(
        spotify=SpotifyIngestionSettings(history_glob="*.json", min_duration_seconds=30),
        lastfm=LastFMIngestionSettings(export_glob="*.csv", dedupe_identical_scrobbles=True),
        apple_music=AppleMusicSettings(),
    )

    settings = Settings(
        metadata=MetadataSettings(environment="test", log_level="ERROR", timezone="UTC"),
        paths=PathSettings(
            raw_spotify_history=raw_spotify,
            raw_lastfm_exports=raw_lastfm,
            raw_apple_music_exports=raw_apple,
            database_path=tmp_path / "playback.sqlite",
            musicbrainz_cache=tmp_path / "musicbrainz.sqlite",
        ),
        ingestion=ingestion,
        enrichment=EnrichmentSettings(),
    )
    return settings


@pytest.fixture
def copy_spotify_fixture(temp_settings: Settings) -> Settings:
    """Copy the sample Spotify JSON fixture into the temp raw directory."""
    target = Path(temp_settings.paths.raw_spotify_history) / "Streaming_History_Audio_0.json"
    shutil.copy(FIXTURES_DIR / "spotify_history.json", target)
    return temp_settings


@pytest.fixture
def copy_lastfm_fixture(temp_settings: Settings) -> Settings:
    """Copy the sample Last.fm CSV fixture into the temp raw directory."""
    target = Path(temp_settings.paths.raw_lastfm_exports) / "recenttracks.csv"
    shutil.copy(FIXTURES_DIR / "lastfm_scrobbles.csv", target)
    return temp_settings


@pytest.fixture
def fetch_table_rows() -> Callable[[Path, str], List[Dict[str, Any]]]:
    """Return a helper to fetch all rows from a SQLite table."""

    def _fetch(db_path: Path, table: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return _fetch


@pytest.fixture
def write_settings_file(tmp_path: Path) -> Callable[[Settings], Path]:
    """Persist a Settings object to disk as TOML for CLI tests."""

    def _write(settings: Settings) -> Path:
        config_text = textwrap.dedent(
            f"""
            [metadata]
            environment = "{settings.metadata.environment}"
            log_level = "{settings.metadata.log_level}"
            timezone = "{settings.metadata.timezone}"

            [paths]
            raw_spotify_history = "{settings.paths.raw_spotify_history}"
            raw_lastfm_exports = "{settings.paths.raw_lastfm_exports}"
            raw_apple_music_exports = "{settings.paths.raw_apple_music_exports}"
            database_path = "{settings.paths.database_path}"
            musicbrainz_cache = "{settings.paths.musicbrainz_cache}"

            [ingestion.spotify]
            history_glob = "{settings.ingestion.spotify.history_glob}"
            min_duration_seconds = {settings.ingestion.spotify.min_duration_seconds}
            skip_podcasts = {str(settings.ingestion.spotify.skip_podcasts).lower()}

            [ingestion.lastfm]
            export_glob = "{settings.ingestion.lastfm.export_glob}"
            dedupe_identical_scrobbles = {str(settings.ingestion.lastfm.dedupe_identical_scrobbles).lower()}

            [ingestion.apple_music]
            library_xml_path = ""
            token = ""

            [enrichment]
            enabled = {str(settings.enrichment.enabled).lower()}
            max_retries = {settings.enrichment.max_retries}
            retry_backoff_seconds = {settings.enrichment.retry_backoff_seconds}

              [enrichment.musicbrainz]
              app_name = "{settings.enrichment.musicbrainz.app_name}"
              rate_limit_per_second = {settings.enrichment.musicbrainz.rate_limit_per_second}
            """
        ).strip()
        target = tmp_path / "settings.toml"
        target.write_text(config_text, encoding="utf-8")
        return target

    return _write
