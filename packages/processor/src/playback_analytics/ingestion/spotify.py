"""Spotify ingestion logic for Extended Streaming History exports."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from dateutil.parser import isoparse
from pydantic import BaseModel, ValidationError
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from playback_analytics.config import Settings
from playback_analytics.db import DatabaseSession, connect

logger = logging.getLogger(__name__)


class SpotifyExtendedPlay(BaseModel):
    """Typed representation of a Spotify Extended Streaming History row."""

    ts: str
    platform: Optional[str] = None
    ms_played: Optional[int] = None
    conn_country: Optional[str] = None
    ip_addr: Optional[str] = None
    master_metadata_track_name: Optional[str] = None
    master_metadata_album_artist_name: Optional[str] = None
    master_metadata_album_album_name: Optional[str] = None
    spotify_track_uri: Optional[str] = None
    episode_name: Optional[str] = None
    episode_show_name: Optional[str] = None
    spotify_episode_uri: Optional[str] = None
    audiobook_title: Optional[str] = None
    audiobook_uri: Optional[str] = None
    audiobook_chapter_uri: Optional[str] = None
    audiobook_chapter_title: Optional[str] = None
    reason_start: Optional[str] = None
    reason_end: Optional[str] = None
    shuffle: Optional[bool] = None
    skipped: Optional[bool] = None
    offline: Optional[bool] = None
    offline_timestamp: Optional[int] = None
    incognito_mode: Optional[bool] = None

    def timestamp(self) -> datetime:
        dt = isoparse(self.ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def is_podcast(self) -> bool:
        return any([self.episode_name, self.episode_show_name, self.spotify_episode_uri])


@dataclass
class SpotifyIngestionStats:
    files_processed: int = 0
    records_seen: int = 0
    inserted: int = 0
    skipped_podcasts: int = 0
    skipped_short: int = 0
    invalid_records: int = 0
    duplicate_rows: int = 0
    metadata_flagged: int = 0
    min_timestamp: Optional[datetime] = None
    max_timestamp: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)
    sample_records: list[dict] = field(default_factory=list)

    def update_range(self, ts: datetime) -> None:
        if self.min_timestamp is None or ts < self.min_timestamp:
            self.min_timestamp = ts
        if self.max_timestamp is None or ts > self.max_timestamp:
            self.max_timestamp = ts

    def record_sample(self, *, ts: datetime, track: Optional[str], artist: Optional[str], source: Path) -> None:
        if len(self.sample_records) >= 3:
            return
        self.sample_records.append(
            {
                "timestamp": ts.isoformat(),
                "track": track,
                "artist": artist,
                "source_file": source.name,
            }
        )

    def to_summary(self) -> dict:
        return {
            "files_processed": self.files_processed,
            "records_seen": self.records_seen,
            "inserted": self.inserted,
            "skipped_podcasts": self.skipped_podcasts,
            "skipped_short": self.skipped_short,
            "invalid_records": self.invalid_records,
            "duplicate_rows": self.duplicate_rows,
            "metadata_flagged": self.metadata_flagged,
            "start_timestamp": self.min_timestamp.isoformat() if self.min_timestamp else None,
            "end_timestamp": self.max_timestamp.isoformat() if self.max_timestamp else None,
            "errors": self.errors,
            "sample_records": self.sample_records,
        }


@contextmanager
def maybe_progress(enabled: bool) -> Iterator[Optional[Progress]]:
    if not enabled:
        yield None
        return
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    )
    with progress:
        yield progress


class SpotifyIngestor:
    """Loads Spotify streaming history exports and upserts raw rows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.raw_path = Path(settings.paths.get_spotify_path())
        self.db_path = settings.paths.database_path
        self.config = settings.ingestion.spotify

    def iter_history_files(self) -> Iterable[Path]:
        """Yield JSON files matching the configured glob."""
        for path in sorted(self.raw_path.glob(self.config.history_glob)):
            if path.is_file():
                yield path

    def load_raw_events(self) -> list[dict]:
        """Load JSON payloads (used by legacy pipeline code)."""
        events: list[dict] = []
        for file_path in self.iter_history_files():
            events.extend(self._load_file_records(file_path))
        return events

    def ingest(self, show_progress: bool = False, dry_run: bool = False) -> SpotifyIngestionStats:
        """Parse files, insert into raw_spotify_plays, and return stats."""
        stats = SpotifyIngestionStats()
        seen_hashes: set[str] = set()
        db_context = nullcontext(None) if dry_run else connect(self.db_path)
        with maybe_progress(show_progress) as progress, db_context as db:
            for file_path in self.iter_history_files():
                stats.files_processed += 1
                records = self._load_file_records(file_path)
                task_id = (
                    progress.add_task(f"Ingesting {file_path.name}", total=len(records))
                    if progress
                    else None
                )
                for idx, raw in enumerate(records, start=1):
                    stats.records_seen += 1
                    try:
                        model = SpotifyExtendedPlay.model_validate(raw)
                        ts_utc = model.timestamp()
                    except (ValidationError, ValueError) as exc:
                        stats.invalid_records += 1
                        message = f"{file_path.name}:{idx} invalid row ({exc})"
                        logger.warning(message)
                        stats.errors.append(message)
                        if progress:
                            progress.advance(task_id, 1)  # type: ignore[arg-type]
                        continue

                    if self.config.skip_podcasts and model.is_podcast():
                        stats.skipped_podcasts += 1
                        if progress:
                            progress.advance(task_id, 1)  # type: ignore[arg-type]
                        continue

                    ms_played = model.ms_played or 0
                    if ms_played < self.config.min_duration_seconds * 1000:
                        stats.skipped_short += 1
                        if progress:
                            progress.advance(task_id, 1)  # type: ignore[arg-type]
                        continue

                    metadata_flags: list[str] = []
                    if not model.master_metadata_track_name:
                        metadata_flags.append("missing_track_name")
                    if not model.master_metadata_album_artist_name:
                        metadata_flags.append("missing_artist_name")
                    if not model.master_metadata_album_album_name:
                        metadata_flags.append("missing_album_name")
                    if not model.spotify_track_uri:
                        metadata_flags.append("missing_track_uri")

                    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True)
                    raw_hash = self._raw_hash(payload)
                    if dry_run:
                        if raw_hash in seen_hashes:
                            stats.duplicate_rows += 1
                        else:
                            seen_hashes.add(raw_hash)
                            stats.inserted += 1
                            stats.update_range(ts_utc)
                            if metadata_flags:
                                stats.metadata_flagged += 1
                            stats.record_sample(
                                ts=ts_utc,
                                track=model.master_metadata_track_name,
                                artist=model.master_metadata_album_artist_name,
                                source=file_path,
                            )
                        if progress:
                            progress.advance(task_id, 1)  # type: ignore[arg-type]
                        continue

                    inserted = self._insert_row(
                        db=db,
                        file_path=file_path,
                        row_number=idx,
                        model=model,
                        ts_utc=ts_utc,
                        metadata_flags=metadata_flags,
                        payload=payload,
                        raw_hash=raw_hash,
                        ms_played=ms_played,
                    )
                    if inserted:
                        stats.inserted += 1
                        stats.update_range(ts_utc)
                        if metadata_flags:
                            stats.metadata_flagged += 1
                        stats.record_sample(
                            ts=ts_utc,
                            track=model.master_metadata_track_name,
                            artist=model.master_metadata_album_artist_name,
                            source=file_path,
                        )
                    else:
                        stats.duplicate_rows += 1

                    if progress:
                        progress.advance(task_id, 1)  # type: ignore[arg-type]

        return stats

    def _insert_row(
        self,
        db: DatabaseSession,
        file_path: Path,
        row_number: int,
        model: SpotifyExtendedPlay,
        ts_utc: datetime,
        metadata_flags: list[str],
        payload: str,
        raw_hash: str,
        ms_played: int,
    ) -> bool:
        def as_int(value: Optional[bool]) -> Optional[int]:
            if value is None:
                return None
            return int(bool(value))

        cursor = db.execute(
            """
            INSERT OR IGNORE INTO raw_spotify_plays (
                source_file,
                source_row,
                play_timestamp_utc,
                ms_played,
                track_name,
                artist_name,
                album_name,
                spotify_track_uri,
                reason_start,
                reason_end,
                shuffle,
                skipped,
                offline,
                offline_timestamp,
                incognito_mode,
                platform,
                conn_country,
                ip_addr,
                metadata_flags,
                json_payload,
                raw_hash
            ) VALUES (
                :source_file,
                :source_row,
                :play_timestamp_utc,
                :ms_played,
                :track_name,
                :artist_name,
                :album_name,
                :spotify_track_uri,
                :reason_start,
                :reason_end,
                :shuffle,
                :skipped,
                :offline,
                :offline_timestamp,
                :incognito_mode,
                :platform,
                :conn_country,
                :ip_addr,
                :metadata_flags,
                :json_payload,
                :raw_hash
            );
            """,
            {
                "source_file": str(file_path),
                "source_row": row_number,
                "play_timestamp_utc": ts_utc.isoformat(),
                "ms_played": ms_played,
                "track_name": model.master_metadata_track_name,
                "artist_name": model.master_metadata_album_artist_name,
                "album_name": model.master_metadata_album_album_name,
                "spotify_track_uri": model.spotify_track_uri,
                "reason_start": model.reason_start,
                "reason_end": model.reason_end,
                "shuffle": as_int(model.shuffle),
                "skipped": as_int(model.skipped),
                "offline": as_int(model.offline),
                "offline_timestamp": (
                    datetime.fromtimestamp(model.offline_timestamp / 1000, UTC).isoformat()
                    if model.offline_timestamp
                    else None
                ),
                "incognito_mode": as_int(model.incognito_mode),
                "platform": model.platform,
                "conn_country": model.conn_country,
                "ip_addr": model.ip_addr,
                "metadata_flags": json.dumps(metadata_flags) if metadata_flags else None,
                "json_payload": payload,
                "raw_hash": raw_hash,
            },
        )
        return cursor.rowcount == 1

    def _load_file_records(self, file_path: Path) -> List[dict]:
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse %s: %s", file_path.name, exc)
            return []

        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]

        if isinstance(data, dict):
            # Some exports wrap rows under a key like "plays".
            rows = data.get("plays")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]

        logger.warning("Unexpected Spotify export structure in %s", file_path)
        return []

    @staticmethod
    def _raw_hash(payload: str) -> str:
        digest = hashlib.sha256()
        digest.update(payload.encode("utf-8"))
        return digest.hexdigest()
