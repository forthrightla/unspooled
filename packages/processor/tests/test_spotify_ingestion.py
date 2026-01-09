"""Tests for Spotify ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner
from playback_analytics.ingestion.spotify import SpotifyIngestor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _ensure_migrated(settings: Settings) -> None:
    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    runner.apply_pending()


def test_spotify_ingestion_happy_path(
    copy_spotify_fixture: Settings, fetch_table_rows
) -> None:
    _ensure_migrated(copy_spotify_fixture)
    ingestor = SpotifyIngestor(copy_spotify_fixture)
    stats = ingestor.ingest(show_progress=False)

    assert stats.records_seen == 6
    assert stats.inserted == 3  # two filtered for podcasts/short play, one invalid timestamp
    assert stats.skipped_short == 1
    assert stats.skipped_podcasts == 1
    assert stats.invalid_records == 1
    assert stats.metadata_flagged >= 1

    rows = fetch_table_rows(copy_spotify_fixture.paths.database_path, "raw_spotify_plays")
    assert len(rows) == stats.inserted

    first_row = rows[0]
    assert first_row["track_name"] == "Eclipse"
    assert first_row["ms_played"] == 215000


def test_spotify_ingestion_dry_run(copy_spotify_fixture: Settings, fetch_table_rows) -> None:
    _ensure_migrated(copy_spotify_fixture)
    ingestor = SpotifyIngestor(copy_spotify_fixture)
    stats = ingestor.ingest(show_progress=False, dry_run=True)

    assert stats.records_seen == 6
    assert stats.inserted == 3

    expected_samples = json.loads(
        (FIXTURES_DIR / "expected_spotify_samples.json").read_text(encoding="utf-8")
    )
    assert stats.sample_records == expected_samples

    rows = fetch_table_rows(copy_spotify_fixture.paths.database_path, "raw_spotify_plays")
    assert rows == []


def test_spotify_ingestion_empty_file(temp_settings: Settings, fetch_table_rows) -> None:
    _ensure_migrated(temp_settings)
    empty_file = temp_settings.paths.raw_spotify_history / "empty.json"
    empty_file.write_text("[]", encoding="utf-8")

    ingestor = SpotifyIngestor(temp_settings)
    stats = ingestor.ingest(show_progress=False)

    assert stats.records_seen == 0
    assert stats.inserted == 0
    rows = fetch_table_rows(temp_settings.paths.database_path, "raw_spotify_plays")
    assert rows == []
