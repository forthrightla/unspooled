"""Last.fm ingestion utilities for CSV exports."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, ValidationError
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from playback_analytics.config import Settings
from playback_analytics.db import DatabaseSession, connect

logger = logging.getLogger(__name__)


class LastFMScrobble(BaseModel):
    """Typed representation of a Last.fm scrobble export row."""

    model_config = ConfigDict(extra="allow")

    uts: Optional[int] = None
    utc_time: Optional[str] = None
    artist_name: Optional[str] = None
    artist_mbid: Optional[str] = None
    album_name: Optional[str] = None
    album_mbid: Optional[str] = None
    track_name: Optional[str] = None
    track_mbid: Optional[str] = None
    duration_seconds: Optional[int] = None
    application: Optional[str] = None

    def timestamp_utc(self, fallback_tz: ZoneInfo) -> datetime:
        if self.uts is not None:
            return datetime.fromtimestamp(self.uts, UTC)
        if self.utc_time:
            parsed = date_parser.parse(self.utc_time)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=fallback_tz)
            return parsed.astimezone(UTC)
        raise ValueError("Missing both `uts` and `utc_time` fields")

    def dedupe_key(self) -> tuple:
        return (
            self.uts or self.utc_time or "",
            (self.artist_name or "").lower(),
            (self.track_name or "").lower(),
        )

    @property
    def album_missing(self) -> bool:
        return not (self.album_name and self.album_name.strip())


@dataclass
class LastFMIngestionStats:
    files_processed: int = 0
    records_seen: int = 0
    inserted: int = 0
    invalid_records: int = 0
    missing_album: int = 0
    duplicates_flagged: int = 0
    duplicates_skipped: int = 0
    min_timestamp: Optional[datetime] = None
    max_timestamp: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)
    sample_records: list[dict] = field(default_factory=list)

    def update_range(self, ts: datetime) -> None:
        if self.min_timestamp is None or ts < self.min_timestamp:
            self.min_timestamp = ts
        if self.max_timestamp is None or ts > self.max_timestamp:
            self.max_timestamp = ts

    def to_summary(self) -> dict:
        return {
            "files_processed": self.files_processed,
            "records_seen": self.records_seen,
            "inserted": self.inserted,
            "invalid_records": self.invalid_records,
            "missing_album": self.missing_album,
            "duplicates_flagged": self.duplicates_flagged,
            "duplicates_skipped": self.duplicates_skipped,
            "start_timestamp": self.min_timestamp.isoformat() if self.min_timestamp else None,
            "end_timestamp": self.max_timestamp.isoformat() if self.max_timestamp else None,
            "errors": self.errors,
            "sample_records": self.sample_records,
        }

    def record_sample(
        self,
        *,
        ts: datetime,
        track: Optional[str],
        artist: Optional[str],
        album: Optional[str],
        source: Path,
    ) -> None:
        if len(self.sample_records) >= 3:
            return
        self.sample_records.append(
            {
                "timestamp": ts.isoformat(),
                "track": track,
                "artist": artist,
                "album": album,
                "source_file": source.name,
            }
        )


@dataclass
class LastFMConfig:
    export_glob: str
    dedupe_identical_scrobbles: bool


class LastFMIngestor:
    """Parse Last.fm CSV exports (recent tracks API dump or user exports)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.raw_path = Path(settings.paths.get_lastfm_path())
        self.db_path = settings.paths.database_path
        self.config = LastFMConfig(
            export_glob=settings.ingestion.lastfm.export_glob,
            dedupe_identical_scrobbles=settings.ingestion.lastfm.dedupe_identical_scrobbles,
        )
        try:
            self.local_timezone = ZoneInfo(settings.metadata.timezone)
        except Exception:  # pragma: no cover - fallback for invalid tz
            logger.warning(
                "Invalid timezone '%s'; defaulting to UTC for Last.fm parsing.",
                settings.metadata.timezone,
            )
            self.local_timezone = ZoneInfo("UTC")

    def iter_export_files(self) -> Iterable[Path]:
        for path in sorted(self.raw_path.glob(self.config.export_glob)):
            if path.is_file():
                yield path

    def load_raw_scrobbles(self) -> list[dict]:
        """Load raw scrobble dicts (used by legacy pipeline code)."""
        scrobbles: list[dict] = []
        for file_path in self.iter_export_files():
            try:
                with file_path.open("r", encoding="utf-8-sig", errors="replace") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        scrobbles.append(self._normalize_row(row))
            except FileNotFoundError:
                logger.warning("File not found: %s", file_path)
        return scrobbles

    def ingest(self, show_progress: bool = False, dry_run: bool = False) -> LastFMIngestionStats:
        stats = LastFMIngestionStats()
        dedupe_keys: set[tuple] = set()
        raw_hashes: set[str] = set()
        db_context = nullcontext(None) if dry_run else connect(self.db_path)
        with self._progress(show_progress) as progress, db_context as db:
            for file_path in self.iter_export_files():
                stats.files_processed += 1
                try:
                    with file_path.open("r", encoding="utf-8-sig", errors="replace") as fh:
                        reader = csv.DictReader(fh)
                        if reader.fieldnames is None:
                            logger.warning("Skipping %s (missing header)", file_path.name)
                            continue
                        task_id = (
                            progress.add_task(f"Ingesting {file_path.name}", total=None)
                            if progress
                            else None
                        )
                        for row in reader:
                            stats.records_seen += 1
                            normalized = self._normalize_row(row)
                            payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
                            try:
                                scrobble = LastFMScrobble.model_validate(normalized)
                                ts_utc = scrobble.timestamp_utc(self.local_timezone)
                            except (ValidationError, ValueError) as exc:
                                stats.invalid_records += 1
                                message = (
                                    f"{file_path.name}:{reader.line_num} invalid row ({exc})"
                                )
                                logger.warning(message)
                                stats.errors.append(message)
                                if progress and task_id is not None:
                                    progress.advance(task_id, 1)
                                continue

                            is_duplicate = scrobble.dedupe_key() in dedupe_keys
                            if is_duplicate:
                                stats.duplicates_flagged += 1
                                if self.config.dedupe_identical_scrobbles:
                                    stats.duplicates_skipped += 1
                                    if progress and task_id is not None:
                                        progress.advance(task_id, 1)
                                    continue

                            dedupe_keys.add(scrobble.dedupe_key())
                            album_missing = scrobble.album_missing
                            if album_missing:
                                stats.missing_album += 1

                            raw_hash = self._raw_hash(file_path, reader.line_num, payload)

                            if dry_run:
                                if raw_hash in raw_hashes:
                                    stats.duplicates_skipped += 1
                                else:
                                    raw_hashes.add(raw_hash)
                                    stats.inserted += 1
                                    stats.update_range(ts_utc)
                                    stats.record_sample(
                                        ts=ts_utc,
                                        track=scrobble.track_name,
                                        artist=scrobble.artist_name,
                                        album=scrobble.album_name,
                                        source=file_path,
                                    )
                                if progress and task_id is not None:
                                    progress.advance(task_id, 1)
                                continue

                            inserted = self._insert_row(
                                db=db,
                                file_path=file_path,
                                line_number=reader.line_num,
                                scrobble=scrobble,
                                ts_utc=ts_utc,
                                payload=payload,
                                album_missing=album_missing,
                                duplicate=is_duplicate,
                                raw_hash=raw_hash,
                            )
                            if inserted:
                                stats.inserted += 1
                                stats.update_range(ts_utc)
                                stats.record_sample(
                                    ts=ts_utc,
                                    track=scrobble.track_name,
                                    artist=scrobble.artist_name,
                                    album=scrobble.album_name,
                                    source=file_path,
                                )
                            else:
                                stats.duplicates_skipped += 1

                            if progress and task_id is not None:
                                progress.advance(task_id, 1)
                except FileNotFoundError:
                    logger.error("File disappeared during ingestion: %s", file_path)

        return stats

    def _insert_row(
        self,
        db: DatabaseSession,
        file_path: Path,
        line_number: int,
        scrobble: LastFMScrobble,
        ts_utc: datetime,
        payload: str,
        album_missing: bool,
        duplicate: bool,
        raw_hash: str,
    ) -> bool:
        cursor = db.execute(
            """
            INSERT OR IGNORE INTO raw_lastfm_scrobbles (
                source_file,
                source_row,
                uts,
                utc_time,
                artist_name,
                artist_mbid,
                album_name,
                album_mbid,
                track_name,
                track_mbid,
                duration_seconds,
                application,
                album_missing,
                duplicate_in_run,
                json_payload,
                raw_hash
            ) VALUES (
                :source_file,
                :source_row,
                :uts,
                :utc_time,
                :artist_name,
                :artist_mbid,
                :album_name,
                :album_mbid,
                :track_name,
                :track_mbid,
                :duration_seconds,
                :application,
                :album_missing,
                :duplicate_in_run,
                :json_payload,
                :raw_hash
            );
            """,
            {
                "source_file": str(file_path),
                "source_row": line_number,
                "uts": scrobble.uts,
                "utc_time": ts_utc.isoformat(),
                "artist_name": scrobble.artist_name,
                "artist_mbid": scrobble.artist_mbid,
                "album_name": scrobble.album_name,
                "album_mbid": scrobble.album_mbid,
                "track_name": scrobble.track_name,
                "track_mbid": scrobble.track_mbid,
                "duration_seconds": scrobble.duration_seconds,
                "application": scrobble.application,
                "album_missing": int(album_missing),
                "duplicate_in_run": int(duplicate),
                "json_payload": payload,
                "raw_hash": raw_hash,
            },
        )
        return cursor.rowcount == 1

    @staticmethod
    def _raw_hash(file_path: Path, line_number: int, payload: str) -> str:
        digest = hashlib.sha256()
        digest.update(str(file_path).encode("utf-8"))
        digest.update(str(line_number).encode("utf-8"))
        digest.update(payload.encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _clean_value(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _normalize_row(self, row: dict[str, str | None]) -> dict:
        lower = { (key or "").strip().lower(): value for key, value in row.items() }

        def pick(*names: str) -> str | None:
            for name in names:
                value = self._clean_value(lower.get(name))
                if value:
                    return value
            return None

        def pick_int(*names: str) -> int | None:
            value = pick(*names)
            if value is None:
                return None
            try:
                return int(float(value))
            except ValueError:
                logger.debug("Unable to parse integer from value '%s'", value)
                return None

        return {
            "uts": pick_int("uts", "timestamp", "unix_timestamp"),
            "utc_time": pick("utc_time", "datetime", "date"),
            "artist_name": pick("artist", "artist_name", "band"),
            "artist_mbid": pick("artist_mbid"),
            "album_name": pick("album", "album_name"),
            "album_mbid": pick("album_mbid"),
            "track_name": pick("track", "track_name", "song"),
            "track_mbid": pick("track_mbid"),
            "duration_seconds": pick_int("duration_seconds", "duration"),
            "application": pick("application", "source", "scrobbler"),
        }

    @contextmanager
    def _progress(self, enabled: bool) -> Iterator[Optional[Progress]]:
        if not enabled:
            yield None
            return
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        )
        with progress:
            yield progress
