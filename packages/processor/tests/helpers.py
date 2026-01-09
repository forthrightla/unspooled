"""Shared helpers for playback analytics tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List


def seed_dedup_sample(db_path: Path) -> Dict[str, any]:
    """Populate canonical tables and plays for deduplication tests."""
    conn = sqlite3.connect(db_path)
    artist_id: int = 0
    album_id: int = 0
    track_id: int = 0
    plays: List[int] = []

    try:
        with conn:
            artist_id = conn.execute(
                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                ("Test Artist", "test-artist"),
            ).lastrowid or 0
            album_id = conn.execute(
                "INSERT INTO canonical_albums (title, normalized_title, primary_artist_id) VALUES (?, ?, ?)",
                ("Test Album", "test-album", artist_id),
            ).lastrowid or 0
            track_id = conn.execute(
                """
                INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id, primary_album_id)
                VALUES (?, ?, ?, ?)
                """,
                ("Test Track", "test-track", artist_id, album_id),
            ).lastrowid or 0

            def add_play(ts: str, duration_ms: int, source: str, source_table: str, source_record_id: int) -> int:
                result = conn.execute(
                    """
                    INSERT INTO plays (
                        canonical_track_id,
                        canonical_album_id,
                        primary_artist_id,
                        play_timestamp_utc,
                        duration_ms,
                        ms_played,
                        source_name,
                        source_record_id,
                        source_row_table
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        track_id,
                        album_id,
                        artist_id,
                        ts,
                        duration_ms,
                        duration_ms,
                        source,
                        source_record_id,
                        source_table,
                    ),
                ).lastrowid
                return result or 0

            plays.append(
                add_play(
                    "2022-01-01T00:00:00+00:00",
                    210_000,
                    "spotify",
                    "raw_spotify_plays",
                    1,
                )
            )
            plays.append(
                add_play(
                    "2022-01-01T00:00:25+00:00",
                    205_000,
                    "lastfm",
                    "raw_lastfm_scrobbles",
                    1,
                )
            )
            plays.append(
                add_play(
                    "2022-01-01T00:05:00+00:00",
                    210_000,
                    "apple_music",
                    "raw_apple_music_plays",
                    1,
                )
            )
            plays.append(
                add_play(
                    "2022-01-01T00:06:05+00:00",
                    200_000,
                    "lastfm",
                    "raw_lastfm_scrobbles",
                    2,
                )
            )
    finally:
        conn.close()

    return {
        "artist_id": artist_id,
        "album_id": album_id,
        "track_id": track_id,
        "play_ids": plays,
    }
