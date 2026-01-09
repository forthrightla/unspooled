"""CLI smoke tests with dry-run mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from playback_analytics.cli import app
from playback_analytics.config import Settings

runner = CliRunner()


def _cli(*args: str):
    return runner.invoke(app, list(args))


def _extract_last_json(stdout: str) -> str:
    text = stdout.rstrip()
    end = text.rfind("}")
    if end == -1:
        raise AssertionError(f"No JSON object found in output:\n{text}")
    depth = 0
    for idx in range(end, -1, -1):
        char = text[idx]
        if char == "}":
            depth += 1
        elif char == "{":
            depth -= 1
            if depth == 0:
                return text[idx : end + 1]
    raise AssertionError(f"Unbalanced JSON braces in output:\n{text}")


def _parse_last_json(stdout: str) -> dict[str, Any]:
    snippet = _extract_last_json(stdout)
    return json.loads(snippet)


def test_cli_ingest_spotify_dry_run(copy_spotify_fixture: Settings, write_settings_file) -> None:
    config_path = write_settings_file(copy_spotify_fixture)
    result = _cli(
        "ingest-spotify",
        "--config",
        str(config_path),
        "--dry-run",
        "--no-progress",
    )
    assert result.exit_code == 0, result.stderr
    payload = _parse_last_json(result.stdout)
    assert payload["inserted"] == 3
    assert payload["sample_records"]


def test_cli_ingest_lastfm_dry_run(copy_lastfm_fixture: Settings, write_settings_file) -> None:
    config_path = write_settings_file(copy_lastfm_fixture)
    result = _cli(
        "ingest-lastfm",
        "--config",
        str(config_path),
        "--dry-run",
        "--no-progress",
    )
    assert result.exit_code == 0
    payload = _parse_last_json(result.stdout)
    assert payload["inserted"] == 4
    assert payload["sample_records"]


def test_cli_migrate_dry_run(temp_settings: Settings, write_settings_file) -> None:
    config_path = write_settings_file(temp_settings)
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    result = _cli(
        "migrate",
        "--config",
        str(config_path),
        "--migrations-dir",
        str(migrations_dir),
        "--dry-run",
    )
    assert result.exit_code == 0
    payload = _parse_last_json(result.stdout)
    assert "migrations" in payload


def test_cli_run_dry_run(temp_settings: Settings, write_settings_file) -> None:
    config_path = write_settings_file(temp_settings)
    result = _cli(
        "run",
        "--config",
        str(config_path),
        "--dry-run",
    )
    assert result.exit_code == 0
    assert "Dry-run" in result.stdout
