"""MusicBrainz enrichment engine tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from playback_analytics.cli import app
from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner
from playback_analytics.enrichment import MusicBrainzEnricher

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
cli_runner = CliRunner()


def _ensure_migrated(settings: Settings) -> None:
    migration_runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    migration_runner.apply_pending()


def _seed_artist(db_path: Path, name: str, mbid: str = None) -> int:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO canonical_artists (name, normalized_name, musicbrainz_mbid)
                VALUES (?, ?, ?)
                """,
                (name, name.lower().replace(" ", "-"), mbid),
            )
            return cursor.lastrowid or 0
    finally:
        conn.close()


def _seed_album(db_path: Path, title: str, artist_id: int, mbid: str = None) -> int:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO canonical_albums (title, normalized_title, primary_artist_id, musicbrainz_mbid)
                VALUES (?, ?, ?, ?)
                """,
                (title, title.lower().replace(" ", "-"), artist_id, mbid),
            )
            return cursor.lastrowid or 0
    finally:
        conn.close()


def _seed_track(db_path: Path, title: str, artist_id: int, album_id: int = None) -> int:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id, primary_album_id)
                VALUES (?, ?, ?, ?)
                """,
                (title, title.lower().replace(" ", "-"), artist_id, album_id),
            )
            return cursor.lastrowid or 0
    finally:
        conn.close()


def _parse_last_json(stdout: str) -> dict[str, Any]:
    text = stdout.rstrip()
    end = text.rfind("}")
    if end == -1:
        raise AssertionError(f"No JSON payload in output:\n{text}")
    depth = 0
    for idx in range(end, -1, -1):
        char = text[idx]
        if char == "}":
            depth += 1
        elif char == "{":
            depth -= 1
            if depth == 0:
                return json.loads(text[idx : end + 1])
    raise AssertionError(f"Malformed JSON in output:\n{text}")


MOCK_ARTIST_SEARCH = {
    "artist-list": [
        {
            "id": "mbid-radiohead-123",
            "name": "Radiohead",
            "type": "Group",
            "country": "GB",
        }
    ]
}

MOCK_ARTIST_DATA = {
    "artist": {
        "id": "mbid-radiohead-123",
        "name": "Radiohead",
        "type": "Group",
        "country": "GB",
        "life-span": {"begin": "1985"},
        "tag-list": [
            {"name": "alternative rock", "count": "100"},
            {"name": "electronic", "count": "80"},
            {"name": "art rock", "count": "60"},
        ],
    }
}

MOCK_RECORDING_SEARCH = {
    "recording-list": [
        {
            "id": "mbid-recording-123",
            "title": "Karma Police",
            "artist-credit": [{"artist": {"id": "mbid-radiohead-123", "name": "Radiohead"}}],
            "release-list": [
                {
                    "id": "mbid-release-456",
                    "title": "OK Computer",
                    "date": "1997-05-21",
                    "release-group": {
                        "id": "mbid-rg-789",
                        "type": "Album",
                        "primary-type": "Album",
                    },
                }
            ],
        }
    ]
}

MOCK_RELEASE_GROUP = {
    "release-group": {
        "id": "mbid-rg-789",
        "title": "OK Computer",
        "first-release-date": "1997-05-21",
        "tag-list": [
            {"name": "alternative rock", "count": "50"},
        ],
    }
}


def test_enricher_status_empty_db(temp_settings: Settings) -> None:
    """Status command works on empty database."""
    _ensure_migrated(temp_settings)
    enricher = MusicBrainzEnricher(temp_settings)
    status = enricher.status()

    assert status["artists"]["total"] == 0
    assert status["albums"]["total"] == 0
    assert status["tracks"]["total"] == 0
    assert status["tags"]["total"] == 0


def test_enricher_status_with_data(temp_settings: Settings) -> None:
    """Status command shows correct coverage statistics."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    artist_id = _seed_artist(db_path, "Radiohead", mbid="mbid-123")
    _seed_artist(db_path, "Unknown Artist")
    _seed_album(db_path, "OK Computer", artist_id, mbid="mbid-456")
    _seed_album(db_path, "No MBID Album", artist_id)
    _seed_track(db_path, "Karma Police", artist_id, album_id=1)
    _seed_track(db_path, "No Album Track", artist_id)

    enricher = MusicBrainzEnricher(temp_settings)
    status = enricher.status()

    assert status["artists"]["total"] == 2
    assert status["artists"]["with_mbid"] == 1
    assert status["albums"]["total"] == 2
    assert status["albums"]["with_mbid"] == 1
    assert status["tracks"]["total"] == 2
    assert status["tracks"]["with_album"] == 1


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_enrich_artists_dry_run(mock_mb: MagicMock, temp_settings: Settings) -> None:
    """Enrich artists in dry-run mode doesn't write to database."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    mock_mb.search_artists.return_value = MOCK_ARTIST_SEARCH
    mock_mb.get_artist_by_id.return_value = MOCK_ARTIST_DATA

    _seed_artist(db_path, "Radiohead")

    enricher = MusicBrainzEnricher(temp_settings)
    stats = enricher.enrich_artists(dry_run=True, limit=10)

    assert stats["artists_processed"] == 1
    assert stats["artists_enriched"] == 1

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT musicbrainz_mbid FROM canonical_artists WHERE name = 'Radiohead'").fetchone()
        assert row[0] is None
    finally:
        conn.close()


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_enrich_artists_writes_data(mock_mb: MagicMock, temp_settings: Settings) -> None:
    """Enrich artists writes MBID, country, type, and tags."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    mock_mb.search_artists.return_value = MOCK_ARTIST_SEARCH
    mock_mb.get_artist_by_id.return_value = MOCK_ARTIST_DATA

    _seed_artist(db_path, "Radiohead")

    enricher = MusicBrainzEnricher(temp_settings)
    stats = enricher.enrich_artists(dry_run=False, limit=10)

    assert stats["artists_enriched"] == 1
    assert stats["tags_added"] >= 1

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT musicbrainz_mbid, country, artist_type FROM canonical_artists WHERE name = 'Radiohead'"
        ).fetchone()
        assert row[0] == "mbid-radiohead-123"
        assert row[1] == "GB"
        assert row[2] == "Group"

        tag_count = conn.execute("SELECT COUNT(*) FROM artist_tags").fetchone()[0]
        assert tag_count >= 1

        tags = conn.execute("SELECT name FROM tags").fetchall()
        tag_names = [t[0] for t in tags]
        assert "alternative rock" in tag_names
    finally:
        conn.close()


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_find_missing_albums_dry_run(mock_mb: MagicMock, temp_settings: Settings) -> None:
    """Find missing albums in dry-run mode doesn't write to database."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    mock_mb.search_recordings.return_value = MOCK_RECORDING_SEARCH

    artist_id = _seed_artist(db_path, "Radiohead")
    _seed_track(db_path, "Karma Police", artist_id, album_id=None)

    enricher = MusicBrainzEnricher(temp_settings)
    stats = enricher.find_missing_albums(dry_run=True, limit=10)

    assert stats["albums_processed"] == 1
    assert stats["albums_found"] == 1

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT primary_album_id FROM canonical_tracks WHERE title = 'Karma Police'").fetchone()
        assert row[0] is None
    finally:
        conn.close()


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_find_missing_albums_creates_album(mock_mb: MagicMock, temp_settings: Settings) -> None:
    """Find missing albums creates new album and links track."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    mock_mb.search_recordings.return_value = MOCK_RECORDING_SEARCH

    artist_id = _seed_artist(db_path, "Radiohead")
    _seed_track(db_path, "Karma Police", artist_id, album_id=None)

    enricher = MusicBrainzEnricher(temp_settings)
    stats = enricher.find_missing_albums(dry_run=False, limit=10)

    assert stats["albums_enriched"] == 1

    conn = sqlite3.connect(db_path)
    try:
        track_row = conn.execute(
            "SELECT primary_album_id FROM canonical_tracks WHERE title = 'Karma Police'"
        ).fetchone()
        assert track_row[0] is not None

        album_row = conn.execute(
            "SELECT title, musicbrainz_mbid FROM canonical_albums WHERE id = ?",
            (track_row[0],),
        ).fetchone()
        assert album_row[0] == "OK Computer"
        assert album_row[1] == "mbid-rg-789"
    finally:
        conn.close()


def test_caching_stores_responses(temp_settings: Settings, fetch_table_rows) -> None:
    """Verify cache stores and retrieves responses."""
    _ensure_migrated(temp_settings)
    enricher = MusicBrainzEnricher(temp_settings)

    test_response = {"test": "data", "nested": {"key": "value"}}
    enricher._set_cache("test-entity", "test-id", "hash123", test_response)

    cached = enricher._get_cached("test-entity", "test-id", "hash123")
    assert cached == test_response

    cache_rows = fetch_table_rows(temp_settings.paths.database_path, "musicbrainz_cache")
    assert len(cache_rows) == 1
    assert cache_rows[0]["entity_type"] == "test-entity"


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_enrich_status_cli(
    mock_mb: MagicMock, temp_settings: Settings, write_settings_file
) -> None:
    """CLI enrich status command returns coverage stats."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["enrich", "status", "--config", str(config_path)],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output
    assert "Artists" in result.stdout
    assert "Albums" in result.stdout
    assert "Tracks" in result.stdout


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_enrich_artists_cli_dry_run(
    mock_mb: MagicMock, temp_settings: Settings, write_settings_file
) -> None:
    """CLI enrich artists command with dry-run."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    mock_mb.search_artists.return_value = MOCK_ARTIST_SEARCH
    mock_mb.get_artist_by_id.return_value = MOCK_ARTIST_DATA

    _seed_artist(temp_settings.paths.database_path, "Radiohead")

    result = cli_runner.invoke(
        app,
        ["enrich", "artists", "--config", str(config_path), "--dry-run", "--limit", "10"],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output with processing info
    assert "Artist Enrichment" in result.stdout
    assert "Artists Processed" in result.stdout
    assert "Dry run" in result.stdout


@patch("playback_analytics.enrichment.enricher.musicbrainzngs")
def test_enrich_all_cli(
    mock_mb: MagicMock, temp_settings: Settings, write_settings_file
) -> None:
    """CLI enrich all command runs full pipeline."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    mock_mb.search_artists.return_value = {"artist-list": []}
    mock_mb.search_recordings.return_value = {"recording-list": []}

    result = cli_runner.invoke(
        app,
        ["enrich", "all", "--config", str(config_path), "--dry-run", "--limit", "5"],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output for all enrichment phases
    assert "Artist Enrichment" in result.stdout
    assert "Album Enrichment" in result.stdout
    assert "Genre Enrichment" in result.stdout
    assert "Dry run" in result.stdout
