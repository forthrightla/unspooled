"""Tests for Last.fm ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner
from playback_analytics.ingestion.lastfm import LastFMIngestor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _ensure_migrated(settings: Settings) -> None:
    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    runner.apply_pending()


def test_lastfm_ingestion_happy_path(copy_lastfm_fixture: Settings, fetch_table_rows) -> None:
    _ensure_migrated(copy_lastfm_fixture)
    ingestor = LastFMIngestor(copy_lastfm_fixture)
    stats = ingestor.ingest(show_progress=False)

    assert stats.records_seen == 6
    assert stats.inserted == 4  # duplicate removed, invalid row skipped
    assert stats.invalid_records == 1
    assert stats.duplicates_flagged >= 1
    assert stats.duplicates_skipped >= 1
    assert stats.missing_album == 1  # Portishead missing album name

    expected_samples = json.loads(
        (FIXTURES_DIR / "expected_lastfm_samples.json").read_text(encoding="utf-8")
    )
    assert stats.sample_records == expected_samples

    rows = fetch_table_rows(copy_lastfm_fixture.paths.database_path, "raw_lastfm_scrobbles")
    assert len(rows) == stats.inserted
    assert rows[0]["track_name"] == "Right Thing"
    assert rows[1]["album_missing"] == 1


def test_lastfm_ingestion_dry_run(copy_lastfm_fixture: Settings, fetch_table_rows) -> None:
    _ensure_migrated(copy_lastfm_fixture)
    ingestor = LastFMIngestor(copy_lastfm_fixture)
    stats = ingestor.ingest(show_progress=False, dry_run=True)

    assert stats.inserted == 4
    assert stats.sample_records
    rows = fetch_table_rows(copy_lastfm_fixture.paths.database_path, "raw_lastfm_scrobbles")
    assert rows == []


def test_lastfm_ingestion_empty_file(temp_settings: Settings, fetch_table_rows) -> None:
    _ensure_migrated(temp_settings)
    empty = temp_settings.paths.raw_lastfm_exports / "empty.csv"
    empty.write_text("uts,artist\n", encoding="utf-8")

    ingestor = LastFMIngestor(temp_settings)
    stats = ingestor.ingest(show_progress=False)

    assert stats.records_seen == 0
    rows = fetch_table_rows(temp_settings.paths.database_path, "raw_lastfm_scrobbles")
    assert rows == []
