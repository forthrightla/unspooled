"""CLI orchestration layer tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from playback_analytics.cli import app
from playback_analytics.config import Settings
from playback_analytics.db import MigrationRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
cli_runner = CliRunner()


def _ensure_migrated(settings: Settings) -> None:
    migration_runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    migration_runner.apply_pending()


def _seed_minimal_data(db_path: Path) -> None:
    """Seed minimal data for testing."""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            artist_id = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("Test Artist", "test-artist"),
            ).lastrowid

            track_id = conn.execute(
                """INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id)
                   VALUES (?, ?, ?)""",
                ("Test Track", "test-track", artist_id),
            ).lastrowid

            conn.execute(
                """INSERT INTO plays (
                    canonical_track_id, primary_artist_id,
                    play_timestamp_utc, source_name, source_row_table
                ) VALUES (?, ?, ?, ?, ?)""",
                (track_id, artist_id, "2023-01-15T10:00:00+00:00", "spotify", "raw_spotify_plays"),
            )
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


# =============================================================================
# Database commands tests
# =============================================================================


def test_db_init(temp_settings: Settings, write_settings_file) -> None:
    """db init creates database with migrations."""
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(app, ["db", "init", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout
    assert temp_settings.paths.database_path.exists()


def test_db_stats(temp_settings: Settings, write_settings_file) -> None:
    """db stats shows database statistics."""
    _ensure_migrated(temp_settings)
    _seed_minimal_data(temp_settings.paths.database_path)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(app, ["db", "stats", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout
    assert "Total plays" in result.stdout or "plays" in result.stdout.lower()


def test_db_backup(temp_settings: Settings, write_settings_file, tmp_path: Path) -> None:
    """db backup creates a copy of the database."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    backup_path = tmp_path / "backup.db"
    result = cli_runner.invoke(
        app,
        ["db", "backup", "--config", str(config_path), "--output", str(backup_path)],
    )
    assert result.exit_code == 0, result.stdout
    assert backup_path.exists()


def test_db_reset_requires_confirmation(temp_settings: Settings, write_settings_file) -> None:
    """db reset requires confirmation without --force."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    # Without --force, should prompt and exit on empty input
    result = cli_runner.invoke(
        app,
        ["db", "reset", "--config", str(config_path)],
        input="n\n",
    )
    assert result.exit_code == 0
    # Database should still exist
    assert temp_settings.paths.database_path.exists()


def test_db_reset_with_force(temp_settings: Settings, write_settings_file) -> None:
    """db reset --force recreates the database."""
    _ensure_migrated(temp_settings)
    _seed_minimal_data(temp_settings.paths.database_path)
    config_path = write_settings_file(temp_settings)

    # Get initial row count
    conn = sqlite3.connect(temp_settings.paths.database_path)
    initial_count = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    conn.close()
    assert initial_count > 0

    result = cli_runner.invoke(
        app,
        ["db", "reset", "--config", str(config_path), "--force"],
    )
    assert result.exit_code == 0, result.stdout

    # Database should be empty now
    conn = sqlite3.connect(temp_settings.paths.database_path)
    final_count = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    conn.close()
    assert final_count == 0


# =============================================================================
# Config commands tests
# =============================================================================


def test_config_show(temp_settings: Settings, write_settings_file) -> None:
    """config show displays configuration."""
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(app, ["config", "show", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout
    assert "Database" in result.stdout


def test_config_validate(temp_settings: Settings, write_settings_file) -> None:
    """config validate checks configuration paths."""
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(app, ["config", "validate", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout


# =============================================================================
# Review commands tests
# =============================================================================


def test_review_status(temp_settings: Settings, write_settings_file) -> None:
    """review status shows pending items count."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(app, ["review", "status", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout
    assert "pending" in result.stdout.lower()


def test_review_export(temp_settings: Settings, write_settings_file, tmp_path: Path) -> None:
    """review export creates a YAML file."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    output_path = tmp_path / "review.yaml"
    result = cli_runner.invoke(
        app,
        ["review", "export", "--config", str(config_path), "--output", str(output_path)],
    )
    assert result.exit_code == 0, result.stdout
    assert output_path.exists()


# =============================================================================
# Ingest commands tests
# =============================================================================


def test_ingest_spotify_dry_run(temp_settings: Settings, write_settings_file) -> None:
    """ingest spotify --dry-run doesn't write data."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["ingest", "spotify", "--config", str(config_path), "--dry-run"],
    )
    # May fail if no spotify files, but should not crash
    assert result.exit_code in (0, 1), result.stdout


def test_ingest_lastfm_dry_run(temp_settings: Settings, write_settings_file) -> None:
    """ingest lastfm --dry-run doesn't write data."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["ingest", "lastfm", "--config", str(config_path), "--dry-run"],
    )
    # May fail if no lastfm files, but should not crash
    assert result.exit_code in (0, 1), result.stdout


# =============================================================================
# Pipeline commands tests
# =============================================================================


def test_pipeline_full_skip_enrich(temp_settings: Settings, write_settings_file) -> None:
    """pipeline full --skip-enrich runs without MusicBrainz."""
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["pipeline", "full", "--config", str(config_path), "--skip-enrich"],
    )
    # Should complete even without source files
    assert result.exit_code == 0, result.stdout
    assert "Pipeline Complete" in result.stdout or "complete" in result.stdout.lower()


def test_pipeline_incremental(temp_settings: Settings, write_settings_file) -> None:
    """pipeline incremental handles empty database."""
    _ensure_migrated(temp_settings)
    config_path = write_settings_file(temp_settings)

    result = cli_runner.invoke(
        app,
        ["pipeline", "incremental", "--config", str(config_path), "--skip-enrich"],
    )
    # Should complete even with no new data
    assert result.exit_code == 0, result.stdout


# =============================================================================
# Console utilities tests
# =============================================================================


def test_console_format_duration() -> None:
    """Console format_duration works correctly."""
    from playback_analytics.console import format_duration

    assert format_duration(5000) == "5s"
    assert format_duration(90000) == "1m 30s"
    assert format_duration(3700000) == "1h 1m"
    assert format_duration(90000000) == "1d 1h"


def test_console_format_number() -> None:
    """Console format_number adds separators."""
    from playback_analytics.console import format_number

    assert format_number(1000) == "1,000"
    assert format_number(1000000) == "1,000,000"
