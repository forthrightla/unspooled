"""Deduplication engine and CLI tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from playback_analytics.cli import app
from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner
from playback_analytics.deduplication import DeduplicationEngine
from tests.helpers import seed_dedup_sample

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
cli_runner = CliRunner()


def _ensure_migrated(settings: Settings) -> None:
    migration_runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    migration_runner.apply_pending()


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


def _prepare_review_pair(db_path: Path, play_id: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE plays SET canonical_album_id = NULL, duration_ms = 260000 WHERE id = ?",
                (play_id,),
            )
    finally:
        conn.close()


def test_deduplication_engine_merges_and_flags(temp_settings: Settings, fetch_table_rows) -> None:
    _ensure_migrated(temp_settings)
    seeded = seed_dedup_sample(temp_settings.paths.database_path)
    # Force the second pair to lose album + duration points so it becomes a review candidate.
    review_play_id = seeded["play_ids"][3]
    _prepare_review_pair(temp_settings.paths.database_path, review_play_id)

    engine = DeduplicationEngine(temp_settings)
    stats = engine.run(window_seconds=60, fuzzy_threshold=0.9, duration_tolerance=0.1)

    assert stats["duplicates_merged"] == 1
    assert stats["flagged_for_review"] == 1

    plays = fetch_table_rows(temp_settings.paths.database_path, "plays")
    duplicates = [row for row in plays if row["is_duplicate"] == 1]
    assert len(duplicates) == 1
    assert duplicates[0]["duplicate_of_id"]

    review_rows = fetch_table_rows(temp_settings.paths.database_path, "dedupe_review_queue")
    assert len(review_rows) == 1
    assert review_rows[0]["confidence"] >= 50


def test_deduplication_cli_commands(
    temp_settings: Settings,
    write_settings_file,
    fetch_table_rows,
    tmp_path: Path,
) -> None:
    _ensure_migrated(temp_settings)
    seeded = seed_dedup_sample(temp_settings.paths.database_path)
    _prepare_review_pair(temp_settings.paths.database_path, seeded["play_ids"][3])
    config_path = write_settings_file(temp_settings)

    # Dry-run execution returns stats in Rich table format
    result = cli_runner.invoke(
        app,
        [
            "dedupe",
            "run",
            "--config",
            str(config_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Plays Considered" in result.stdout or "plays_considered" in result.stdout

    # Real run writes dedupe markers and review queue entries
    result = cli_runner.invoke(
        app,
        [
            "dedupe",
            "run",
            "--config",
            str(config_path),
        ],
    )
    assert result.exit_code == 0, result.stdout

    # Report command returns aggregate metrics in Rich table format
    result = cli_runner.invoke(
        app,
        [
            "dedupe",
            "report",
            "--config",
            str(config_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Duplicates Marked" in result.stdout or "duplicates_marked" in result.stdout

    # Review export writes a YAML file
    review_output = tmp_path / "dedupe_review.yaml"
    result = cli_runner.invoke(
        app,
        [
            "dedupe",
            "review",
            "--config",
            str(config_path),
            "--output",
            str(review_output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert review_output.exists()

    queue_rows = fetch_table_rows(temp_settings.paths.database_path, "dedupe_review_queue")
    assert queue_rows, "Review queue should contain borderline matches"

    # Undo clears duplicate flags and review queue entries
    result = cli_runner.invoke(
        app,
        [
            "dedupe",
            "undo",
            "--config",
            str(config_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    # Check for Rich table output
    assert "Deduplication Undo" in result.stdout or "Plays Reset" in result.stdout

    plays = fetch_table_rows(temp_settings.paths.database_path, "plays")
    assert all(row["is_duplicate"] == 0 for row in plays)
    queue_rows = fetch_table_rows(temp_settings.paths.database_path, "dedupe_review_queue")
    assert queue_rows == []


def test_deduplication_no_plays(temp_settings: Settings) -> None:
    """Engine handles empty plays table gracefully."""
    _ensure_migrated(temp_settings)
    engine = DeduplicationEngine(temp_settings)
    stats = engine.run(dry_run=True)
    assert stats["plays_considered"] == 0
    assert stats["duplicates_merged"] == 0


def test_deduplication_no_duplicates(temp_settings: Settings, fetch_table_rows) -> None:
    """Engine handles plays with no duplicates (different tracks or too far apart)."""
    _ensure_migrated(temp_settings)
    conn = sqlite3.connect(temp_settings.paths.database_path)
    try:
        with conn:
            artist_id = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("Solo Artist", "solo-artist"),
            ).lastrowid
            track_a = conn.execute(
                "INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id) VALUES (?, ?, ?)",
                ("Track A", "track-a", artist_id),
            ).lastrowid
            track_b = conn.execute(
                "INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id) VALUES (?, ?, ?)",
                ("Track B", "track-b", artist_id),
            ).lastrowid
            # Two plays of different tracks - should not match
            conn.execute(
                """
                INSERT INTO plays (canonical_track_id, primary_artist_id, play_timestamp_utc, source_name, source_row_table)
                VALUES (?, ?, ?, ?, ?)
                """,
                (track_a, artist_id, "2022-01-01T00:00:00+00:00", "spotify", "raw_spotify_plays"),
            )
            conn.execute(
                """
                INSERT INTO plays (canonical_track_id, primary_artist_id, play_timestamp_utc, source_name, source_row_table)
                VALUES (?, ?, ?, ?, ?)
                """,
                (track_b, artist_id, "2022-01-01T00:00:10+00:00", "lastfm", "raw_lastfm_scrobbles"),
            )
    finally:
        conn.close()

    engine = DeduplicationEngine(temp_settings)
    stats = engine.run()
    assert stats["plays_considered"] == 2
    assert stats["duplicates_merged"] == 0
    assert stats["flagged_for_review"] == 0

    plays = fetch_table_rows(temp_settings.paths.database_path, "plays")
    assert all(row["is_duplicate"] == 0 for row in plays)


def test_deduplication_source_priority(temp_settings: Settings, fetch_table_rows) -> None:
    """Verify Spotify wins over Last.fm when both have same track at same time."""
    _ensure_migrated(temp_settings)
    seeded = seed_dedup_sample(temp_settings.paths.database_path)

    engine = DeduplicationEngine(temp_settings)
    engine.run()

    plays = fetch_table_rows(temp_settings.paths.database_path, "plays")
    duplicates = [row for row in plays if row["is_duplicate"] == 1]
    winners = [row for row in plays if row["is_duplicate"] == 0 and row["duplicate_of_id"] is None]

    # Both lastfm plays should be marked as duplicates (seed has 2 pairs that merge)
    # Pair 1: Spotify (00:00:00) vs Last.fm (00:00:25) - 25s apart, 90 points
    # Pair 2: Apple Music (00:05:00) vs Last.fm (00:06:05) - 65s apart, 70 points
    assert len(duplicates) == 2
    assert all(d["source_name"] == "lastfm" for d in duplicates)
    # Higher priority sources (Spotify, Apple Music) should be winners
    assert len(winners) == 2
    winner_sources = {w["source_name"] for w in winners}
    assert winner_sources == {"spotify", "apple_music"}
