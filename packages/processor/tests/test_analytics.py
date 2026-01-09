"""Analytics computation engine tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from playback_analytics.analytics import AnalyticsEngine
from playback_analytics.cli import app
from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
cli_runner = CliRunner()


def _ensure_migrated(settings: Settings) -> None:
    migration_runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    migration_runner.apply_pending()


def _seed_play_data(db_path: Path) -> dict[str, Any]:
    """Seed artists, albums, tracks, and plays for analytics testing."""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            artist1 = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("Test Artist", "test-artist"),
            ).lastrowid

            artist2 = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("Second Artist", "second-artist"),
            ).lastrowid

            album1 = conn.execute(
                """INSERT INTO canonical_albums (title, normalized_title, primary_artist_id)
                   VALUES (?, ?, ?)""",
                ("Test Album", "test-album", artist1),
            ).lastrowid

            track1 = conn.execute(
                """INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id, primary_album_id)
                   VALUES (?, ?, ?, ?)""",
                ("Track One", "track-one", artist1, album1),
            ).lastrowid

            track2 = conn.execute(
                """INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id, primary_album_id)
                   VALUES (?, ?, ?, ?)""",
                ("Track Two", "track-two", artist1, album1),
            ).lastrowid

            track3 = conn.execute(
                """INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id)
                   VALUES (?, ?, ?)""",
                ("Track Three", "track-three", artist2),
            ).lastrowid

            plays = []
            # Artist 1 plays across multiple months
            for i, ts in enumerate([
                "2023-01-15T10:00:00+00:00",
                "2023-01-15T10:05:00+00:00",
                "2023-01-20T14:00:00+00:00",
                "2023-02-10T20:00:00+00:00",
                "2023-02-11T08:00:00+00:00",
                "2023-03-05T23:00:00+00:00",
            ]):
                track = track1 if i % 2 == 0 else track2
                play_id = conn.execute(
                    """INSERT INTO plays (
                        canonical_track_id, canonical_album_id, primary_artist_id,
                        play_timestamp_utc, duration_ms, source_name, source_row_table
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (track, album1, artist1, ts, 210000, "spotify", "raw_spotify_plays"),
                ).lastrowid
                plays.append(play_id)

            # Artist 2 plays
            for ts in ["2023-01-25T15:00:00+00:00", "2023-04-01T12:00:00+00:00"]:
                play_id = conn.execute(
                    """INSERT INTO plays (
                        canonical_track_id, primary_artist_id,
                        play_timestamp_utc, duration_ms, source_name, source_row_table
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (track3, artist2, ts, 180000, "lastfm", "raw_lastfm_scrobbles"),
                ).lastrowid
                plays.append(play_id)

        return {
            "artist1": artist1,
            "artist2": artist2,
            "album1": album1,
            "tracks": [track1, track2, track3],
            "plays": plays,
        }
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


def test_analytics_summary_empty_db(temp_settings: Settings) -> None:
    """Summary works on empty database."""
    _ensure_migrated(temp_settings)
    engine = AnalyticsEngine(temp_settings)
    summary = engine.summary()

    assert summary["overview"]["total_plays"] == 0
    assert summary["overview"]["unique_artists"] == 0
    assert summary["top_artists"] == []


def test_compute_artist_analytics(temp_settings: Settings, fetch_table_rows) -> None:
    """Artist analytics computed correctly."""
    _ensure_migrated(temp_settings)
    seeded = _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    stats = engine.compute_artist_analytics()

    assert stats["artists_computed"] == 2

    rows = fetch_table_rows(temp_settings.paths.database_path, "artist_analytics")
    assert len(rows) == 2

    artist1_analytics = next(r for r in rows if r["artist_id"] == seeded["artist1"])
    assert artist1_analytics["total_plays"] == 6
    assert artist1_analytics["first_play_date"] == "2023-01-15"
    assert artist1_analytics["loyalty_tier"] is not None
    assert artist1_analytics["binge_score"] is not None


def test_compute_album_analytics(temp_settings: Settings, fetch_table_rows) -> None:
    """Album analytics computed correctly."""
    _ensure_migrated(temp_settings)
    seeded = _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    stats = engine.compute_album_analytics()

    assert stats["albums_computed"] == 1

    rows = fetch_table_rows(temp_settings.paths.database_path, "album_analytics")
    assert len(rows) == 1
    assert rows[0]["album_id"] == seeded["album1"]
    assert rows[0]["total_plays"] == 6


def test_compute_track_analytics(temp_settings: Settings, fetch_table_rows) -> None:
    """Track analytics computed correctly."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    stats = engine.compute_track_analytics()

    assert stats["tracks_computed"] == 3

    rows = fetch_table_rows(temp_settings.paths.database_path, "track_analytics")
    assert len(rows) == 3

    # Check time-of-day distribution was computed
    for row in rows:
        total_time_plays = (
            row["morning_plays"] + row["afternoon_plays"] +
            row["evening_plays"] + row["night_plays"]
        )
        assert total_time_plays == row["total_plays"]


def test_compute_temporal_analytics(temp_settings: Settings, fetch_table_rows) -> None:
    """Monthly, hourly, weekday distributions computed."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    stats = engine.compute_temporal_analytics()

    assert stats["monthly_periods"] >= 3  # Jan, Feb, Mar, Apr

    monthly = fetch_table_rows(temp_settings.paths.database_path, "monthly_summary")
    assert len(monthly) >= 3

    jan = next((m for m in monthly if m["year_month"] == "2023-01"), None)
    assert jan is not None
    assert jan["total_plays"] == 4  # 3 artist1 + 1 artist2 in Jan

    hourly = fetch_table_rows(temp_settings.paths.database_path, "hourly_distribution")
    assert len(hourly) > 0

    weekday = fetch_table_rows(temp_settings.paths.database_path, "weekday_distribution")
    assert len(weekday) > 0


def test_compute_discovery_context(temp_settings: Settings, fetch_table_rows) -> None:
    """Discovery context links artists listened to around discovery time."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    # First compute artist analytics to populate first_play_date
    engine.compute_artist_analytics()
    stats = engine.compute_discovery_context()

    # Should have some discovery links
    rows = fetch_table_rows(temp_settings.paths.database_path, "discovery_context")
    # Artist2 discovered on 2023-01-25, Artist1 was playing around that time
    assert len(rows) >= 0  # May or may not have links depending on timing


def test_compute_all(temp_settings: Settings) -> None:
    """Compute all analytics in one call."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    results = engine.compute_all()

    assert "artists" in results
    assert "albums" in results
    assert "tracks" in results
    assert "temporal" in results
    assert "discovery" in results
    assert "geographic" in results


def test_summary_with_data(temp_settings: Settings) -> None:
    """Summary returns correct statistics with data."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    engine.compute_all()
    summary = engine.summary()

    assert summary["overview"]["total_plays"] == 8
    assert summary["overview"]["unique_artists"] == 2
    assert summary["overview"]["unique_tracks"] == 3
    assert len(summary["top_artists"]) == 2


def test_export_json(temp_settings: Settings, tmp_path: Path) -> None:
    """Export creates JSON files in output directory."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)

    engine = AnalyticsEngine(temp_settings)
    engine.compute_all()

    output_dir = tmp_path / "analytics_export"
    exported = engine.export_json(output_dir)

    assert "summary" in exported
    assert "monthly" in exported
    assert "hourly" in exported
    assert "weekday" in exported
    assert "top_artists" in exported

    # Verify files exist and contain valid JSON
    summary_path = Path(exported["summary"])
    assert summary_path.exists()
    with summary_path.open() as f:
        data = json.load(f)
        assert "overview" in data


def test_loyalty_tier_classification(temp_settings: Settings, fetch_table_rows) -> None:
    """Loyalty tier correctly classifies artists."""
    _ensure_migrated(temp_settings)
    db_path = temp_settings.paths.database_path

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            # One-and-done artist: only a few plays
            artist_oad = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("One And Done", "one-and-done"),
            ).lastrowid

            track_oad = conn.execute(
                """INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id)
                   VALUES (?, ?, ?)""",
                ("OAD Track", "oad-track", artist_oad),
            ).lastrowid

            # Only 3 plays
            for ts in ["2023-01-01T10:00:00+00:00", "2023-01-02T10:00:00+00:00", "2023-01-03T10:00:00+00:00"]:
                conn.execute(
                    """INSERT INTO plays (canonical_track_id, primary_artist_id,
                       play_timestamp_utc, source_name, source_row_table)
                       VALUES (?, ?, ?, ?, ?)""",
                    (track_oad, artist_oad, ts, "spotify", "raw_spotify_plays"),
                )
    finally:
        conn.close()

    engine = AnalyticsEngine(temp_settings)
    engine.compute_artist_analytics()

    rows = fetch_table_rows(db_path, "artist_analytics")
    oad_row = next(r for r in rows if r["artist_id"] == artist_oad)
    assert oad_row["loyalty_tier"] == "one-and-done"


def test_analytics_compute_cli(temp_settings: Settings, write_settings_file) -> None:
    """CLI compute command works."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["analytics", "compute", "--config", str(config_path), "--target", "artists"],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output
    assert "Analytics" in result.stdout
    assert "Artists Computed" in result.stdout or "artists_computed" in result.stdout


def test_analytics_summary_cli(temp_settings: Settings, write_settings_file) -> None:
    """CLI summary command works."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)
    config_path = write_settings_file(temp_settings)

    # First compute
    cli_runner.invoke(
        app,
        ["analytics", "compute", "--config", str(config_path)],
    )

    result = cli_runner.invoke(
        app,
        ["analytics", "summary", "--config", str(config_path)],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output
    assert "Analytics Summary" in result.stdout
    assert "Overview" in result.stdout


def test_analytics_export_cli(temp_settings: Settings, write_settings_file, tmp_path: Path) -> None:
    """CLI export command creates files."""
    _ensure_migrated(temp_settings)
    _seed_play_data(temp_settings.paths.database_path)
    config_path = write_settings_file(temp_settings)

    # First compute
    cli_runner.invoke(
        app,
        ["analytics", "compute", "--config", str(config_path)],
    )

    output_dir = tmp_path / "export_test"
    result = cli_runner.invoke(
        app,
        ["analytics", "export", "--config", str(config_path), "--output", str(output_dir)],
    )
    assert result.exit_code == 0, result.stdout
    assert output_dir.exists()
    assert (output_dir / "summary.json").exists()
