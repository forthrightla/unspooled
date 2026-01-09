"""MusicBrainz enrichment engine for filling missing metadata."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import certifi

# Fix SSL certificate verification on macOS before importing musicbrainzngs
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import musicbrainzngs
from rapidfuzz import fuzz

from rich import print as rprint

from playback_analytics.config import Settings
from playback_analytics.db import connect

logger = logging.getLogger(__name__)

# Suppress verbose musicbrainzngs INFO logs
logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)


@dataclass
class EnrichmentStats:
    artists_processed: int = 0
    artists_enriched: int = 0
    albums_processed: int = 0
    albums_enriched: int = 0
    albums_found: int = 0
    tags_added: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    api_errors: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    # Progress tracking
    total_items: int = 0
    current_item: int = 0
    current_entity_name: str = ""
    estimated_seconds_remaining: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artists_processed": self.artists_processed,
            "artists_enriched": self.artists_enriched,
            "albums_processed": self.albums_processed,
            "albums_enriched": self.albums_enriched,
            "albums_found": self.albums_found,
            "tags_added": self.tags_added,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "api_errors": self.api_errors,
            "skipped": self.skipped,
            "errors": self.errors[:10],
        }


ProgressCallback = Optional[callable]


class MusicBrainzEnricher:
    """Enrich canonical entities with MusicBrainz metadata."""

    CACHE_EXPIRY_DAYS = 30

    def __init__(self, settings: Settings, use_local_db: bool = True) -> None:
        self.settings = settings
        self.db_path = settings.paths.database_path
        mb_settings = settings.enrichment.musicbrainz
        self.rate_limit = mb_settings.rate_limit_per_second
        self.last_request_time: float = 0.0
        
        # Try to use local MusicBrainz database if available
        self.local_db = None
        if use_local_db:
            local_db_path = settings.paths.database_path.parent / "musicbrainz_local.sqlite"
            if local_db_path.exists():
                from playback_analytics.enrichment.local_mb import LocalMusicBrainzDB
                self.local_db = LocalMusicBrainzDB(local_db_path)
                status = self.local_db.get_import_status()
                if status:
                    rprint(f"[cyan]Using local MusicBrainz DB ({sum(s.get('record_count', 0) for s in status.values()):,} records)[/]")

        musicbrainzngs.set_useragent(
            mb_settings.app_name.split("/")[0],
            mb_settings.app_name.split("/")[1].split(" ")[0] if "/" in mb_settings.app_name else "0.1",
            mb_settings.app_name.split("(")[1].rstrip(")") if "(" in mb_settings.app_name else "contact@example.com",
        )

    def _respect_rate_limit(self) -> None:
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        elapsed = time.perf_counter() - self.last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request_time = time.perf_counter()

    def _cache_key(self, entity_type: str, query: str, params: Dict[str, Any]) -> str:
        params_str = json.dumps(params, sort_keys=True)
        return hashlib.sha256(f"{entity_type}:{query}:{params_str}".encode()).hexdigest()

    def _get_cached(self, entity_type: str, entity_id: str, params_hash: str) -> Optional[Dict[str, Any]]:
        with connect(self.db_path) as db:
            row = db.execute(
                """
                SELECT response_json, fetched_at, expires_at
                FROM musicbrainz_cache
                WHERE entity_type = ? AND entity_id = ? AND params_hash = ?
                """,
                (entity_type, entity_id, params_hash),
            ).fetchone()
            if row:
                expires_at = row["expires_at"]
                if expires_at:
                    expiry = datetime.fromisoformat(expires_at)
                    if expiry < datetime.now(UTC):
                        return None
                return json.loads(row["response_json"])
        return None

    def _set_cache(
        self, entity_type: str, entity_id: str, params_hash: str, response: Dict[str, Any]
    ) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(days=self.CACHE_EXPIRY_DAYS)
        with connect(self.db_path) as db:
            db.execute(
                """
                INSERT OR REPLACE INTO musicbrainz_cache
                (entity_type, entity_id, params_hash, response_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_type,
                    entity_id,
                    params_hash,
                    json.dumps(response),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )

    def _search_recording(
        self, artist: str, track: str, stats: EnrichmentStats
    ) -> Optional[Dict[str, Any]]:
        # Use local DB if available
        if self.local_db:
            recording = self.local_db.find_recording(track, artist)
            if recording:
                stats.cache_hits += 1
                # Convert local format to API-like format
                recording_list = [{
                    "id": recording["id"],
                    "title": recording["title"],
                    "length": recording.get("length"),
                    "artist-credit": recording.get("artist-credit", []),
                    "release-list": [
                        {
                            "id": r.get("release_mbid"),
                            "title": r.get("release_title"),
                            "release-group": {
                                "id": r.get("release_group_mbid"),
                                "title": r.get("release_group_title"),
                            },
                            "date": r.get("date"),
                        }
                        for r in recording.get("releases", [])
                    ],
                }]
                return {"recording-list": recording_list}
            stats.cache_misses += 1
            return None
        
        cache_key = self._cache_key("recording-search", f"{artist}:{track}", {})
        cached = self._get_cached("recording-search", f"{artist}:{track}", cache_key)
        if cached:
            stats.cache_hits += 1
            return cached

        stats.cache_misses += 1
        self._respect_rate_limit()
        try:
            result = musicbrainzngs.search_recordings(
                recording=track,
                artist=artist,
                limit=10,
            )
            self._set_cache("recording-search", f"{artist}:{track}", cache_key, result)
            return result
        except musicbrainzngs.WebServiceError as e:
            stats.api_errors += 1
            stats.errors.append(f"Recording search error for {artist} - {track}: {e}")
            logger.warning("MusicBrainz search error: %s", e)
            return None

    def _search_artist(self, artist_name: str, stats: EnrichmentStats) -> Optional[Dict[str, Any]]:
        # Use local DB if available
        if self.local_db:
            artist = self.local_db.find_artist(artist_name)
            if artist:
                stats.cache_hits += 1
                return {"artist-list": [artist]}
            # Try fuzzy search
            artists = self.local_db.find_artist_fuzzy(artist_name, limit=5)
            if artists:
                stats.cache_hits += 1
                return {"artist-list": artists}
            stats.cache_misses += 1
            return None
        
        cache_key = self._cache_key("artist-search", artist_name, {})
        cached = self._get_cached("artist-search", artist_name, cache_key)
        if cached:
            stats.cache_hits += 1
            return cached

        stats.cache_misses += 1
        self._respect_rate_limit()
        try:
            result = musicbrainzngs.search_artists(artist=artist_name, limit=5)
            self._set_cache("artist-search", artist_name, cache_key, result)
            return result
        except musicbrainzngs.WebServiceError as e:
            stats.api_errors += 1
            stats.errors.append(f"Artist search error for {artist_name}: {e}")
            logger.warning("MusicBrainz artist search error: %s", e)
            return None

    def _get_artist_by_mbid(
        self, mbid: str, stats: EnrichmentStats, includes: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        # Use local DB if available
        if self.local_db:
            artist = self.local_db.get_artist_by_mbid(mbid)
            if artist:
                stats.cache_hits += 1
                return {"artist": artist}
            stats.cache_misses += 1
            return None
        
        includes = includes or ["tags", "ratings"]
        params_hash = self._cache_key("artist", mbid, {"inc": includes})
        cached = self._get_cached("artist", mbid, params_hash)
        if cached:
            stats.cache_hits += 1
            return cached

        stats.cache_misses += 1
        self._respect_rate_limit()
        try:
            result = musicbrainzngs.get_artist_by_id(mbid, includes=includes)
            self._set_cache("artist", mbid, params_hash, result)
            return result
        except musicbrainzngs.WebServiceError as e:
            stats.api_errors += 1
            stats.errors.append(f"Artist fetch error for MBID {mbid}: {e}")
            logger.warning("MusicBrainz artist fetch error: %s", e)
            return None

    def _get_release_group(
        self, mbid: str, stats: EnrichmentStats
    ) -> Optional[Dict[str, Any]]:
        # Use local DB if available
        if self.local_db:
            rg = self.local_db.get_release_group_by_mbid(mbid)
            if rg:
                stats.cache_hits += 1
                return {"release-group": rg}
            stats.cache_misses += 1
            return None
        
        includes = ["tags", "ratings", "artist-credits"]
        params_hash = self._cache_key("release-group", mbid, {"inc": includes})
        cached = self._get_cached("release-group", mbid, params_hash)
        if cached:
            stats.cache_hits += 1
            return cached

        stats.cache_misses += 1
        self._respect_rate_limit()
        try:
            result = musicbrainzngs.get_release_group_by_id(mbid, includes=includes)
            self._set_cache("release-group", mbid, params_hash, result)
            return result
        except musicbrainzngs.WebServiceError as e:
            stats.api_errors += 1
            stats.errors.append(f"Release group fetch error for MBID {mbid}: {e}")
            logger.warning("MusicBrainz release-group fetch error: %s", e)
            return None

    def _score_artist_match(self, query: str, result: Dict[str, Any]) -> float:
        name = result.get("name", "")
        score = fuzz.ratio(query.lower(), name.lower()) / 100.0
        if result.get("disambiguation"):
            score *= 0.95
        if result.get("type") == "Group":
            score *= 1.02
        return min(score, 1.0)

    def _score_recording_match(
        self, artist: str, track: str, result: Dict[str, Any]
    ) -> float:
        title = result.get("title", "")
        track_score = fuzz.ratio(track.lower(), title.lower()) / 100.0

        artist_credits = result.get("artist-credit", [])
        artist_names = [ac.get("artist", {}).get("name", "") for ac in artist_credits if isinstance(ac, dict)]
        artist_score = max(
            (fuzz.ratio(artist.lower(), name.lower()) / 100.0 for name in artist_names),
            default=0.0,
        )

        combined = (track_score * 0.6) + (artist_score * 0.4)

        if result.get("releases"):
            combined *= 1.05
        return min(combined, 1.0)

    def _find_best_artist(
        self, artist_name: str, stats: EnrichmentStats
    ) -> Optional[Tuple[str, float]]:
        search_result = self._search_artist(artist_name, stats)
        if not search_result:
            return None

        artists = search_result.get("artist-list", [])
        if not artists:
            return None

        best_match = None
        best_score = 0.0
        for artist in artists:
            score = self._score_artist_match(artist_name, artist)
            if score > best_score:
                best_score = score
                best_match = artist

        if best_match and best_score >= 0.8:
            return best_match.get("id"), best_score
        return None

    def _find_album_for_track(
        self, artist: str, track: str, stats: EnrichmentStats
    ) -> Optional[Dict[str, Any]]:
        search_result = self._search_recording(artist, track, stats)
        if not search_result:
            return None

        recordings = search_result.get("recording-list", [])
        if not recordings:
            return None

        best_recording = None
        best_score = 0.0
        for recording in recordings:
            score = self._score_recording_match(artist, track, recording)
            if score > best_score:
                best_score = score
                best_recording = recording

        if not best_recording or best_score < 0.7:
            return None

        releases = best_recording.get("release-list", [])
        if not releases:
            return None

        studio_albums = [
            r for r in releases
            if r.get("release-group", {}).get("type") == "Album"
            and r.get("release-group", {}).get("primary-type") == "Album"
        ]
        if studio_albums:
            releases = studio_albums

        release = releases[0]
        return {
            "album_title": release.get("title"),
            "release_mbid": release.get("id"),
            "release_group_mbid": release.get("release-group", {}).get("id"),
            "recording_mbid": best_recording.get("id"),
            "confidence": best_score,
            "release_date": release.get("date"),
        }

    def _get_or_create_tag(self, tag_name: str) -> int:
        normalized = tag_name.lower().strip()
        with connect(self.db_path) as db:
            row = db.execute(
                "SELECT id FROM tags WHERE normalized_name = ?", (normalized,)
            ).fetchone()
            if row:
                return row["id"]
            cursor = db.execute(
                "INSERT OR IGNORE INTO tags (name, normalized_name) VALUES (?, ?)",
                (tag_name, normalized),
            )
            if cursor.lastrowid:
                return cursor.lastrowid
            # If INSERT was ignored, fetch the existing id
            row = db.execute(
                "SELECT id FROM tags WHERE normalized_name = ?", (normalized,)
            ).fetchone()
            return row["id"]

    def _log_enrichment(
        self,
        entity_type: str,
        entity_id: int,
        enrichment_type: str,
        confidence: Optional[float],
        status: str,
        notes: Optional[str] = None,
    ) -> None:
        with connect(self.db_path) as db:
            db.execute(
                """
                INSERT OR IGNORE INTO enrichment_log
                (entity_type, entity_id, enrichment_type, confidence, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_type, entity_id, enrichment_type, confidence, status, notes),
            )

    def enrich_artists(
        self,
        *,
        dry_run: bool = False,
        limit: Optional[int] = None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        stats = EnrichmentStats()

        with connect(self.db_path) as db:
            query = """
                SELECT id, name, normalized_name, musicbrainz_mbid, country, artist_type
                FROM canonical_artists
                WHERE musicbrainz_mbid IS NULL
                   OR country IS NULL
                   OR artist_type IS NULL
                ORDER BY id
            """
            if limit:
                query += " LIMIT ?"
                artists = db.execute(query, (limit,)).fetchall()
            else:
                artists = db.execute(query).fetchall()

        stats.total_items = len(artists)
        # Estimate: ~2 API calls per artist at rate_limit requests/sec
        api_calls_per_item = 2
        seconds_per_call = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0
        stats.estimated_seconds_remaining = len(artists) * api_calls_per_item * seconds_per_call

        for idx, artist in enumerate(artists):
            stats.current_item = idx + 1
            stats.current_entity_name = artist["name"][:50]
            remaining = stats.total_items - idx
            stats.estimated_seconds_remaining = remaining * api_calls_per_item * seconds_per_call

            if progress_callback:
                progress_callback(stats)

            stats.artists_processed += 1
            artist_id = artist["id"]
            artist_name = artist["name"]

            if artist["musicbrainz_mbid"]:
                mbid = artist["musicbrainz_mbid"]
                confidence = 1.0
            else:
                match = self._find_best_artist(artist_name, stats)
                if not match:
                    rprint(f"  [dim]- {artist_name[:40]} (not found)[/]")
                    stats.skipped += 1
                    continue
                mbid, confidence = match

            artist_data = self._get_artist_by_mbid(mbid, stats)
            if not artist_data:
                rprint(f"  [dim]- {artist_name[:40]} (no data)[/]")
                stats.skipped += 1
                continue

            mb_artist = artist_data.get("artist", {})
            country = mb_artist.get("country")
            artist_type = mb_artist.get("type")
            # Life span dates extracted for future use
            _ = mb_artist.get("life-span", {}).get("begin")  # begin_date
            _ = mb_artist.get("life-span", {}).get("end")  # end_date

            if dry_run:
                stats.artists_enriched += 1
                continue

            with connect(self.db_path) as db:
                db.execute(
                    """
                    UPDATE OR IGNORE canonical_artists
                    SET musicbrainz_mbid = COALESCE(musicbrainz_mbid, ?),
                        country = COALESCE(country, ?),
                        artist_type = COALESCE(artist_type, ?)
                    WHERE id = ?
                    """,
                    (mbid, country, artist_type, artist_id),
                )

            tags = mb_artist.get("tag-list", [])
            tag_names = [t.get("name") for t in tags[:5] if t.get("name")]
            tags_str = ", ".join(tag_names) if tag_names else "none"
            rprint(f"  [green]✓[/] {artist_name[:40]} [dim]({country or '?'}, {artist_type or '?'})[/] [cyan]{tags_str}[/]")

            for tag in tags[:10]:
                tag_name = tag.get("name")
                tag_score = int(tag.get("count", 0))
                if tag_name:
                    tag_id = self._get_or_create_tag(tag_name)
                    with connect(self.db_path) as db:
                        db.execute(
                            """
                            INSERT OR IGNORE INTO artist_tags (artist_id, tag_id, score)
                            VALUES (?, ?, ?)
                            """,
                            (artist_id, tag_id, tag_score),
                        )
                    stats.tags_added += 1

            self._log_enrichment("artist", artist_id, "metadata", confidence, "success")
            stats.artists_enriched += 1

        return stats.to_dict()

    def enrich_albums(
        self,
        *,
        dry_run: bool = False,
        limit: Optional[int] = None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        stats = EnrichmentStats()

        with connect(self.db_path) as db:
            query = """
                SELECT id, title, normalized_title, primary_artist_id, musicbrainz_mbid, release_date
                FROM canonical_albums
                WHERE musicbrainz_mbid IS NULL OR release_date IS NULL
                ORDER BY id
            """
            if limit:
                query += " LIMIT ?"
                albums = db.execute(query, (limit,)).fetchall()
            else:
                albums = db.execute(query).fetchall()

        stats.total_items = len(albums)
        api_calls_per_item = 1
        seconds_per_call = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0

        for idx, album in enumerate(albums):
            stats.current_item = idx + 1
            stats.current_entity_name = album["title"][:50] if album["title"] else ""
            remaining = stats.total_items - idx
            stats.estimated_seconds_remaining = remaining * api_calls_per_item * seconds_per_call

            if progress_callback:
                progress_callback(stats)

            stats.albums_processed += 1
            album_id = album["id"]

            if album["musicbrainz_mbid"]:
                rg_data = self._get_release_group(album["musicbrainz_mbid"], stats)
                if rg_data:
                    rg = rg_data.get("release-group", {})
                    release_date = rg.get("first-release-date")

                    if not dry_run and release_date:
                        with connect(self.db_path) as db:
                            db.execute(
                                "UPDATE OR IGNORE canonical_albums SET release_date = ? WHERE id = ?",
                                (release_date, album_id),
                            )

                    tags = rg.get("tag-list", [])
                    if not dry_run:
                        for tag in tags[:10]:
                            tag_name = tag.get("name")
                            tag_score = int(tag.get("count", 0))
                            if tag_name:
                                tag_id = self._get_or_create_tag(tag_name)
                                with connect(self.db_path) as db:
                                    db.execute(
                                        """
                                        INSERT OR IGNORE INTO album_tags (album_id, tag_id, score)
                                        VALUES (?, ?, ?)
                                        """,
                                        (album_id, tag_id, tag_score),
                                    )
                                stats.tags_added += 1

                    album_title = album["title"][:35] if album["title"] else "?"
                    tag_names = [t.get("name") for t in tags[:3] if t.get("name")]
                    tags_str = ", ".join(tag_names) if tag_names else ""
                    rprint(f"  [green]✓[/] {album_title} [dim]({release_date or '?'})[/] [cyan]{tags_str}[/]")
                    self._log_enrichment("album", album_id, "metadata", 1.0, "success")
                    stats.albums_enriched += 1
            else:
                rprint(f"  [dim]- {album['title'][:35] if album['title'] else '?'} (no MBID)[/]")
                stats.skipped += 1

        return stats.to_dict()

    def find_missing_albums(
        self,
        *,
        dry_run: bool = False,
        limit: Optional[int] = None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        stats = EnrichmentStats()

        with connect(self.db_path) as db:
            query = """
                SELECT DISTINCT
                    ct.id AS track_id,
                    ct.title AS track_title,
                    ca.name AS artist_name,
                    ct.primary_album_id
                FROM canonical_tracks ct
                JOIN canonical_artists ca ON ca.id = ct.primary_artist_id
                WHERE ct.primary_album_id IS NULL
            """
            if limit:
                query += " LIMIT ?"
                tracks = db.execute(query, (limit,)).fetchall()
            else:
                tracks = db.execute(query).fetchall()

        stats.total_items = len(tracks)
        api_calls_per_item = 1
        seconds_per_call = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0

        for idx, track in enumerate(tracks):
            stats.current_item = idx + 1
            stats.current_entity_name = track["track_title"][:50] if track["track_title"] else ""
            remaining = stats.total_items - idx
            stats.estimated_seconds_remaining = remaining * api_calls_per_item * seconds_per_call

            if progress_callback:
                progress_callback(stats)

            stats.albums_processed += 1
            track_id = track["track_id"]
            artist_name = track["artist_name"]
            track_title = track["track_title"]

            album_info = self._find_album_for_track(artist_name, track_title, stats)
            if not album_info:
                rprint(f"  [dim]- {track_title[:35]} (not found)[/]")
                stats.skipped += 1
                continue

            stats.albums_found += 1
            if dry_run:
                rprint(f"  [yellow]~[/] {track_title[:35]} [dim]→[/] {album_info['album_title'][:25]} [dim]({album_info['confidence']:.0%})[/]")
                continue

            with connect(self.db_path) as db:
                # Check for existing album by MusicBrainz ID first, then by title/artist
                release_group_mbid = album_info.get("release_group_mbid")
                existing = None
                if release_group_mbid:
                    existing = db.execute(
                        "SELECT id FROM canonical_albums WHERE musicbrainz_mbid = ?",
                        (release_group_mbid,),
                    ).fetchone()

                if not existing:
                    existing = db.execute(
                        """
                        SELECT id FROM canonical_albums
                        WHERE normalized_title = lower(?) AND primary_artist_id = (
                            SELECT primary_artist_id FROM canonical_tracks WHERE id = ?
                        )
                        """,
                        (album_info["album_title"], track_id),
                    ).fetchone()

                if existing:
                    album_id = existing["id"]
                else:
                    artist_id_row = db.execute(
                        "SELECT primary_artist_id FROM canonical_tracks WHERE id = ?",
                        (track_id,),
                    ).fetchone()
                    artist_id = artist_id_row["primary_artist_id"] if artist_id_row else None

                    cursor = db.execute(
                        """
                        INSERT OR IGNORE INTO canonical_albums
                        (title, normalized_title, primary_artist_id, musicbrainz_mbid, release_date)
                        VALUES (?, lower(?), ?, ?, ?)
                        """,
                        (
                            album_info["album_title"],
                            album_info["album_title"],
                            artist_id,
                            release_group_mbid,
                            album_info.get("release_date"),
                        ),
                    )
                    album_id = cursor.lastrowid or db.execute(
                        "SELECT id FROM canonical_albums WHERE musicbrainz_mbid = ?",
                        (release_group_mbid,),
                    ).fetchone()["id"]

                db.execute(
                    "UPDATE OR IGNORE canonical_tracks SET primary_album_id = ? WHERE id = ?",
                    (album_id, track_id),
                )

                if album_info.get("recording_mbid"):
                    db.execute(
                        "UPDATE OR IGNORE canonical_tracks SET musicbrainz_recording_mbid = ? WHERE id = ?",
                        (album_info["recording_mbid"], track_id),
                    )

            rprint(f"  [green]✓[/] {track_title[:35]} [dim]→[/] {album_info['album_title'][:25]} [dim]({album_info.get('release_date') or '?'})[/]")

            self._log_enrichment(
                "track", track_id, "album_lookup", album_info["confidence"], "success"
            )
            stats.albums_enriched += 1

        return stats.to_dict()

    def enrich_genres(
        self,
        *,
        dry_run: bool = False,
        limit: Optional[int] = None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        stats = EnrichmentStats()

        with connect(self.db_path) as db:
            query = """
                SELECT ca.id, ca.name, ca.musicbrainz_mbid
                FROM canonical_artists ca
                LEFT JOIN artist_tags at ON at.artist_id = ca.id
                WHERE ca.musicbrainz_mbid IS NOT NULL
                  AND at.artist_id IS NULL
                ORDER BY ca.id
            """
            if limit:
                query += " LIMIT ?"
                artists = db.execute(query, (limit,)).fetchall()
            else:
                artists = db.execute(query).fetchall()

        stats.total_items = len(artists)
        api_calls_per_item = 1
        seconds_per_call = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0

        for idx, artist in enumerate(artists):
            stats.current_item = idx + 1
            stats.current_entity_name = artist["name"][:50] if artist["name"] else ""
            remaining = stats.total_items - idx
            stats.estimated_seconds_remaining = remaining * api_calls_per_item * seconds_per_call

            if progress_callback:
                progress_callback(stats)

            stats.artists_processed += 1
            artist_id = artist["id"]
            mbid = artist["musicbrainz_mbid"]

            artist_data = self._get_artist_by_mbid(mbid, stats, includes=["tags"])
            if not artist_data:
                rprint(f"  [dim]- {artist['name'][:40]} (no data)[/]")
                stats.skipped += 1
                continue

            tags = artist_data.get("artist", {}).get("tag-list", [])
            if not tags:
                rprint(f"  [dim]- {artist['name'][:40]} (no tags)[/]")
                stats.skipped += 1
                continue

            if dry_run:
                stats.artists_enriched += 1
                continue

            tag_names = [t.get("name") for t in tags[:5] if t.get("name")]
            tags_str = ", ".join(tag_names) if tag_names else "none"
            rprint(f"  [green]✓[/] {artist['name'][:40]} [cyan]{tags_str}[/]")

            for tag in tags[:15]:
                tag_name = tag.get("name")
                tag_score = int(tag.get("count", 0))
                if tag_name:
                    tag_id = self._get_or_create_tag(tag_name)
                    with connect(self.db_path) as db:
                        db.execute(
                            """
                            INSERT OR IGNORE INTO artist_tags (artist_id, tag_id, score)
                            VALUES (?, ?, ?)
                            """,
                            (artist_id, tag_id, tag_score),
                        )
                    stats.tags_added += 1

            self._log_enrichment("artist", artist_id, "tags", 1.0, "success")
            stats.artists_enriched += 1

        return stats.to_dict()

    def enrich_all(self, *, dry_run: bool = False, limit: int = 50) -> Dict[str, Any]:
        results = {}
        results["artists"] = self.enrich_artists(dry_run=dry_run, limit=limit)
        results["missing_albums"] = self.find_missing_albums(dry_run=dry_run, limit=limit)
        results["albums"] = self.enrich_albums(dry_run=dry_run, limit=limit)
        results["genres"] = self.enrich_genres(dry_run=dry_run, limit=limit)
        return results

    def status(self) -> Dict[str, Any]:
        with connect(self.db_path) as db:
            total_artists = db.execute("SELECT COUNT(*) AS c FROM canonical_artists").fetchone()["c"]
            artists_with_mbid = db.execute(
                "SELECT COUNT(*) AS c FROM canonical_artists WHERE musicbrainz_mbid IS NOT NULL"
            ).fetchone()["c"]
            artists_with_tags = db.execute(
                "SELECT COUNT(DISTINCT artist_id) AS c FROM artist_tags"
            ).fetchone()["c"]

            total_albums = db.execute("SELECT COUNT(*) AS c FROM canonical_albums").fetchone()["c"]
            albums_with_mbid = db.execute(
                "SELECT COUNT(*) AS c FROM canonical_albums WHERE musicbrainz_mbid IS NOT NULL"
            ).fetchone()["c"]
            albums_with_date = db.execute(
                "SELECT COUNT(*) AS c FROM canonical_albums WHERE release_date IS NOT NULL"
            ).fetchone()["c"]

            total_tracks = db.execute("SELECT COUNT(*) AS c FROM canonical_tracks").fetchone()["c"]
            tracks_with_album = db.execute(
                "SELECT COUNT(*) AS c FROM canonical_tracks WHERE primary_album_id IS NOT NULL"
            ).fetchone()["c"]
            tracks_with_mbid = db.execute(
                "SELECT COUNT(*) AS c FROM canonical_tracks WHERE musicbrainz_recording_mbid IS NOT NULL"
            ).fetchone()["c"]

            total_tags = db.execute("SELECT COUNT(*) AS c FROM tags").fetchone()["c"]
            cache_entries = db.execute("SELECT COUNT(*) AS c FROM musicbrainz_cache").fetchone()["c"]

            recent_enrichments = db.execute(
                """
                SELECT enrichment_type, status, COUNT(*) AS c
                FROM enrichment_log
                WHERE created_at > datetime('now', '-7 days')
                GROUP BY enrichment_type, status
                """
            ).fetchall()

        return {
            "artists": {
                "total": total_artists,
                "with_mbid": artists_with_mbid,
                "with_tags": artists_with_tags,
                "coverage_pct": round(artists_with_mbid / total_artists * 100, 1) if total_artists else 0,
            },
            "albums": {
                "total": total_albums,
                "with_mbid": albums_with_mbid,
                "with_release_date": albums_with_date,
                "coverage_pct": round(albums_with_mbid / total_albums * 100, 1) if total_albums else 0,
            },
            "tracks": {
                "total": total_tracks,
                "with_album": tracks_with_album,
                "with_mbid": tracks_with_mbid,
                "album_coverage_pct": round(tracks_with_album / total_tracks * 100, 1) if total_tracks else 0,
            },
            "tags": {"total": total_tags},
            "cache": {"entries": cache_entries},
            "recent_enrichments": [
                {"type": r["enrichment_type"], "status": r["status"], "count": r["c"]}
                for r in recent_enrichments
            ],
        }
