"""Analytics computation engine for pre-calculated insights."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ProgressCallback = Optional[Callable[["AnalyticsStats"], None]]

from playback_analytics.config import Settings
from playback_analytics.db import connect

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsStats:
    artists_computed: int = 0
    albums_computed: int = 0
    tracks_computed: int = 0
    monthly_periods: int = 0
    discovery_links: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    # Progress tracking
    total_items: int = 0
    current_item: int = 0
    current_entity_name: str = ""
    estimated_seconds_remaining: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artists_computed": self.artists_computed,
            "albums_computed": self.albums_computed,
            "tracks_computed": self.tracks_computed,
            "monthly_periods": self.monthly_periods,
            "discovery_links": self.discovery_links,
            "skipped": self.skipped,
            "errors": self.errors[:10],
        }


class AnalyticsEngine:
    """Compute and store pre-calculated analytics from play data."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.paths.database_path

    def _log_computation(
        self, computation_type: str, entities: int, status: str, notes: str = None
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with connect(self.db_path) as db:
            cursor = db.execute(
                """
                INSERT INTO analytics_computation_log
                (computation_type, entities_processed, started_at, completed_at, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (computation_type, entities, now, now, status, notes),
            )
            return cursor.lastrowid or 0

    def compute_artist_analytics(
        self, *, resume: bool = True, progress_callback: ProgressCallback = None
    ) -> Dict[str, Any]:
        """Compute analytics for all artists with plays.
        
        Uses bulk SQL for all data, then computes complex metrics in Python.
        
        Args:
            resume: If True, skip artists that already have computed analytics.
            progress_callback: Optional callback for progress updates.
        """
        stats = AnalyticsStats()
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        with connect(self.db_path) as db:
            if not resume:
                db.execute("DELETE FROM artist_analytics")

            # PHASE 1: Bulk insert basic stats (~2 seconds)
            logger.info("Phase 1: Bulk inserting basic artist stats...")
            db.execute(
                """
                INSERT OR REPLACE INTO artist_analytics 
                (artist_id, first_play_date, last_play_date, total_plays, total_duration_ms,
                 unique_tracks_played, days_since_last_play, computed_at)
                SELECT 
                    p.primary_artist_id,
                    MIN(date(p.play_timestamp_utc)),
                    MAX(date(p.play_timestamp_utc)),
                    COUNT(*),
                    COALESCE(SUM(COALESCE(p.duration_ms, p.ms_played, 0)), 0),
                    COUNT(DISTINCT p.canonical_track_id),
                    CAST(julianday('now') - julianday(MAX(date(p.play_timestamp_utc))) AS INTEGER),
                    ?
                FROM plays p
                WHERE p.primary_artist_id IS NOT NULL AND p.is_duplicate = 0
                GROUP BY p.primary_artist_id
                """,
                (now_iso,),
            )
            bulk_inserted = db.execute("SELECT changes()").fetchone()[0]
            logger.info("Bulk inserted %d artist basic stats", bulk_inserted)

            # PHASE 2: Bulk fetch ALL data needed for complex metrics (~5 seconds each)
            logger.info("Phase 2: Bulk fetching data for complex metrics...")
            
            # Get artists to process
            if resume:
                artists = db.execute(
                    """
                    SELECT artist_id, first_play_date, last_play_date, total_plays
                    FROM artist_analytics
                    WHERE peak_period_start IS NULL OR loyalty_tier IS NULL
                    """
                ).fetchall()
            else:
                artists = db.execute(
                    "SELECT artist_id, first_play_date, last_play_date, total_plays FROM artist_analytics"
                ).fetchall()
            
            artist_ids = {row["artist_id"] for row in artists}
            artist_data = {row["artist_id"]: dict(row) for row in artists}
            
            # Bulk fetch: monthly plays per artist (for peak_period + loyalty_tier)
            logger.info("  Fetching monthly play counts...")
            monthly_rows = db.execute(
                """
                SELECT primary_artist_id, strftime('%Y-%m', play_timestamp_utc) AS month, COUNT(*) AS plays
                FROM plays
                WHERE primary_artist_id IS NOT NULL AND is_duplicate = 0
                GROUP BY primary_artist_id, month
                """
            ).fetchall()
            monthly_by_artist: Dict[int, List[tuple]] = {}
            for row in monthly_rows:
                aid = row["primary_artist_id"]
                if aid in artist_ids:
                    monthly_by_artist.setdefault(aid, []).append((row["month"], row["plays"]))
            
            # Bulk fetch: track plays per artist (for deep_cuts_ratio)
            logger.info("  Fetching track play counts...")
            track_rows = db.execute(
                """
                SELECT primary_artist_id, canonical_track_id, COUNT(*) AS plays
                FROM plays
                WHERE primary_artist_id IS NOT NULL AND canonical_track_id IS NOT NULL AND is_duplicate = 0
                GROUP BY primary_artist_id, canonical_track_id
                """
            ).fetchall()
            tracks_by_artist: Dict[int, List[int]] = {}
            for row in track_rows:
                aid = row["primary_artist_id"]
                if aid in artist_ids:
                    tracks_by_artist.setdefault(aid, []).append(row["plays"])
            
            # Bulk fetch: first 30 days plays per artist (for binge_score)
            logger.info("  Fetching first-30-days play counts...")
            binge_rows = db.execute(
                """
                SELECT p.primary_artist_id, COUNT(*) AS plays
                FROM plays p
                JOIN artist_analytics aa ON p.primary_artist_id = aa.artist_id
                WHERE p.is_duplicate = 0
                  AND date(p.play_timestamp_utc) BETWEEN aa.first_play_date 
                      AND date(aa.first_play_date, '+30 days')
                GROUP BY p.primary_artist_id
                """
            ).fetchall()
            binge_by_artist = {row["primary_artist_id"]: row["plays"] for row in binge_rows}
            
            # Bulk fetch: daily plays per artist (for discovery_half_life)
            logger.info("  Fetching daily play counts...")
            daily_rows = db.execute(
                """
                SELECT primary_artist_id, date(play_timestamp_utc) AS play_date, COUNT(*) AS plays
                FROM plays
                WHERE primary_artist_id IS NOT NULL AND is_duplicate = 0
                GROUP BY primary_artist_id, play_date
                ORDER BY primary_artist_id, play_date
                """
            ).fetchall()
            daily_by_artist: Dict[int, List[tuple]] = {}
            for row in daily_rows:
                aid = row["primary_artist_id"]
                if aid in artist_ids:
                    daily_by_artist.setdefault(aid, []).append((row["play_date"], row["plays"]))

            # PHASE 3: Compute complex metrics in Python (fast, no DB queries)
            logger.info("Phase 3: Computing complex metrics for %d artists...", len(artists))
            stats.total_items = len(artists)
            stats.skipped = bulk_inserted - len(artists) if resume else 0
            
            updates = []
            for idx, row in enumerate(artists):
                artist_id = row["artist_id"]
                first_play = row["first_play_date"]
                last_play = row["last_play_date"]
                total_plays = row["total_plays"]

                stats.current_item = idx + 1
                if progress_callback and idx % 500 == 0:
                    progress_callback(stats)

                if not first_play or total_plays == 0:
                    continue

                try:
                    # Compute from cached data - NO database queries
                    monthly = monthly_by_artist.get(artist_id, [])
                    tracks = tracks_by_artist.get(artist_id, [])
                    binge_plays = binge_by_artist.get(artist_id, 0)
                    daily = daily_by_artist.get(artist_id, [])
                    
                    binge_score = round(binge_plays / 30.0, 3)
                    peak_start, peak_end = self._calc_peak_period(monthly)
                    loyalty_tier = self._calc_loyalty_tier(monthly, first_play, last_play, total_plays)
                    deep_cuts_ratio = self._calc_deep_cuts_ratio(tracks)
                    discovery_half_life = self._calc_discovery_half_life(daily, first_play, total_plays)

                    updates.append((peak_start, peak_end, binge_score, loyalty_tier, 
                                   deep_cuts_ratio, discovery_half_life, artist_id))
                    stats.artists_computed += 1
                except Exception as e:
                    stats.errors.append(f"Artist {artist_id}: {e}")

            # Batch update all at once
            logger.info("Phase 4: Batch updating %d artists...", len(updates))
            db.executemany(
                """
                UPDATE artist_analytics SET
                    peak_period_start = ?, peak_period_end = ?, binge_score = ?,
                    loyalty_tier = ?, deep_cuts_ratio = ?, discovery_half_life = ?
                WHERE artist_id = ?
                """,
                updates,
            )

        self._log_computation("artist_analytics", stats.artists_computed, "completed")
        return stats.to_dict()

    def _calc_peak_period(self, monthly: List[tuple]) -> tuple[Optional[str], Optional[str]]:
        """Calculate peak period from pre-fetched monthly data."""
        if not monthly:
            return None, None
        peak_month, _ = max(monthly, key=lambda x: x[1])
        start = f"{peak_month}-01"
        year, month = map(int, peak_month.split("-"))
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        return start, end_date.strftime("%Y-%m-%d")

    def _calc_loyalty_tier(self, monthly: List[tuple], first_play: str, last_play: str, total_plays: int) -> str:
        """Calculate loyalty tier from pre-fetched monthly data."""
        if total_plays <= 5:
            return "one-and-done"
        
        first_date = datetime.fromisoformat(first_play).date()
        last_date = datetime.fromisoformat(last_play).date()
        span_days = (last_date - first_date).days + 1
        
        if span_days < 30:
            return "phase"
        
        if len(monthly) <= 1:
            return "phase"
        
        plays_list = [m[1] for m in monthly]
        avg_plays = sum(plays_list) / len(plays_list)
        variance = sum((p - avg_plays) ** 2 for p in plays_list) / len(plays_list)
        std_dev = variance ** 0.5
        cv = std_dev / avg_plays if avg_plays > 0 else 0
        
        months_with_plays = len([p for p in plays_list if p > 0])
        consistency = months_with_plays / len(monthly)
        
        if consistency >= 0.7 and cv < 0.8:
            return "constant"
        elif consistency >= 0.3:
            return "seasonal"
        return "phase"

    def _calc_deep_cuts_ratio(self, track_plays: List[int]) -> float:
        """Calculate deep cuts ratio from pre-fetched track play counts."""
        if len(track_plays) <= 5:
            return 0.0
        sorted_plays = sorted(track_plays, reverse=True)
        top_5_plays = sum(sorted_plays[:5])
        total_plays = sum(sorted_plays)
        deep_cuts_plays = total_plays - top_5_plays
        return round(deep_cuts_plays / total_plays, 3) if total_plays > 0 else 0.0

    def _calc_discovery_half_life(self, daily: List[tuple], first_play_date: str, total_plays: int) -> Optional[int]:
        """Calculate discovery half-life from pre-fetched daily data."""
        if not daily or total_plays == 0:
            return None
        half_target = total_plays / 2
        running = 0
        first_date = datetime.fromisoformat(first_play_date).date()
        for play_date, plays in daily:
            running += plays
            if running >= half_target:
                pd = datetime.fromisoformat(play_date).date()
                return (pd - first_date).days
        return None

    def _compute_binge_score(self, db, artist_id: int, first_play_date: str) -> float:
        first_date = datetime.fromisoformat(first_play_date).date()
        end_date = first_date + timedelta(days=30)
        plays_in_30_days = db.execute(
            """
            SELECT COUNT(*) AS c FROM plays
            WHERE primary_artist_id = ? AND is_duplicate = 0
              AND date(play_timestamp_utc) BETWEEN ? AND ?
            """,
            (artist_id, first_play_date, end_date.isoformat()),
        ).fetchone()["c"]
        return round(plays_in_30_days / 30.0, 3)

    def _compute_peak_period(self, db, artist_id: int) -> tuple[Optional[str], Optional[str]]:
        monthly = db.execute(
            """
            SELECT strftime('%Y-%m', play_timestamp_utc) AS month, COUNT(*) AS plays
            FROM plays
            WHERE primary_artist_id = ? AND is_duplicate = 0
            GROUP BY month
            ORDER BY plays DESC
            LIMIT 1
            """,
            (artist_id,),
        ).fetchone()

        if not monthly:
            return None, None

        peak_month = monthly["month"]
        start = f"{peak_month}-01"
        year, month = map(int, peak_month.split("-"))
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        return start, end_date.strftime("%Y-%m-%d")

    def _compute_loyalty_tier(
        self, db, artist_id: int, first_play: str, last_play: str, total_plays: int
    ) -> str:
        if total_plays <= 5:
            return "one-and-done"

        first_date = datetime.fromisoformat(first_play).date()
        last_date = datetime.fromisoformat(last_play).date()
        span_days = (last_date - first_date).days + 1

        if span_days < 30:
            return "phase"

        monthly_counts = db.execute(
            """
            SELECT strftime('%Y-%m', play_timestamp_utc) AS month, COUNT(*) AS plays
            FROM plays
            WHERE primary_artist_id = ? AND is_duplicate = 0
            GROUP BY month
            """,
            (artist_id,),
        ).fetchall()

        if len(monthly_counts) <= 1:
            return "phase"

        plays_list = [m["plays"] for m in monthly_counts]
        avg_plays = sum(plays_list) / len(plays_list)
        variance = sum((p - avg_plays) ** 2 for p in plays_list) / len(plays_list)
        std_dev = variance ** 0.5
        cv = std_dev / avg_plays if avg_plays > 0 else 0

        months_with_plays = len([p for p in plays_list if p > 0])
        total_months = len(monthly_counts)
        consistency = months_with_plays / total_months if total_months > 0 else 0

        if consistency >= 0.7 and cv < 0.8:
            return "constant"
        elif consistency >= 0.3:
            return "seasonal"
        else:
            return "phase"

    def _compute_deep_cuts_ratio(self, db, artist_id: int) -> float:
        track_plays = db.execute(
            """
            SELECT canonical_track_id, COUNT(*) AS plays
            FROM plays
            WHERE primary_artist_id = ? AND is_duplicate = 0 AND canonical_track_id IS NOT NULL
            GROUP BY canonical_track_id
            ORDER BY plays DESC
            """,
            (artist_id,),
        ).fetchall()

        if len(track_plays) <= 5:
            return 0.0

        top_5_plays = sum(t["plays"] for t in track_plays[:5])
        total_plays = sum(t["plays"] for t in track_plays)
        deep_cuts_plays = total_plays - top_5_plays
        return round(deep_cuts_plays / total_plays, 3) if total_plays > 0 else 0.0

    def _compute_discovery_half_life(self, db, artist_id: int, first_play_date: str) -> Optional[int]:
        cumulative = db.execute(
            """
            SELECT date(play_timestamp_utc) AS play_date, COUNT(*) AS daily_plays
            FROM plays
            WHERE primary_artist_id = ? AND is_duplicate = 0
            GROUP BY play_date
            ORDER BY play_date
            """,
            (artist_id,),
        ).fetchall()

        if not cumulative:
            return None

        total = sum(r["daily_plays"] for r in cumulative)
        half_target = total / 2
        running = 0
        first_date = datetime.fromisoformat(first_play_date).date()

        for row in cumulative:
            running += row["daily_plays"]
            if running >= half_target:
                play_date = datetime.fromisoformat(row["play_date"]).date()
                return (play_date - first_date).days

        return None

    def compute_album_analytics(
        self, *, resume: bool = True, progress_callback: ProgressCallback = None
    ) -> Dict[str, Any]:
        """Compute analytics for all albums with plays.
        
        Uses bulk SQL for all data, then computes completion_rate in Python.
        
        Args:
            resume: If True, skip albums that already have computed analytics.
            progress_callback: Optional callback for progress updates.
        """
        stats = AnalyticsStats()
        now_iso = datetime.now(UTC).isoformat()

        with connect(self.db_path) as db:
            if not resume:
                db.execute("DELETE FROM album_analytics")

            # PHASE 1: Bulk insert basic stats
            logger.info("Phase 1: Bulk inserting album basic stats...")
            db.execute(
                """
                INSERT OR REPLACE INTO album_analytics 
                (album_id, first_play_date, last_play_date, total_plays, total_duration_ms,
                 unique_tracks_played, computed_at)
                SELECT 
                    p.canonical_album_id,
                    MIN(date(p.play_timestamp_utc)),
                    MAX(date(p.play_timestamp_utc)),
                    COUNT(*),
                    COALESCE(SUM(COALESCE(p.duration_ms, p.ms_played, 0)), 0),
                    COUNT(DISTINCT p.canonical_track_id),
                    ?
                FROM plays p
                WHERE p.canonical_album_id IS NOT NULL AND p.is_duplicate = 0
                GROUP BY p.canonical_album_id
                """,
                (now_iso,),
            )
            bulk_inserted = db.execute("SELECT changes()").fetchone()[0]
            logger.info("Bulk inserted %d album basic stats", bulk_inserted)

            # PHASE 2: Bulk fetch data for completion_rate
            logger.info("Phase 2: Bulk fetching data for completion rates...")
            
            if resume:
                albums = db.execute(
                    "SELECT album_id FROM album_analytics WHERE completion_rate IS NULL"
                ).fetchall()
            else:
                albums = db.execute("SELECT album_id FROM album_analytics").fetchall()
            
            album_ids = {row["album_id"] for row in albums}
            
            # Bulk fetch: track counts per album
            logger.info("  Fetching track counts...")
            track_counts = db.execute(
                "SELECT primary_album_id, COUNT(*) AS c FROM canonical_tracks GROUP BY primary_album_id"
            ).fetchall()
            track_count_by_album = {row["primary_album_id"]: row["c"] for row in track_counts}
            
            # Bulk fetch: all plays for albums (for session analysis)
            logger.info("  Fetching album plays...")
            plays_rows = db.execute(
                """
                SELECT canonical_album_id, play_timestamp_utc, canonical_track_id
                FROM plays
                WHERE canonical_album_id IS NOT NULL AND is_duplicate = 0
                ORDER BY canonical_album_id, play_timestamp_utc
                """
            ).fetchall()
            plays_by_album: Dict[int, List[tuple]] = {}
            for row in plays_rows:
                aid = row["canonical_album_id"]
                if aid in album_ids:
                    plays_by_album.setdefault(aid, []).append(
                        (row["play_timestamp_utc"], row["canonical_track_id"])
                    )

            # PHASE 3: Compute completion_rate in Python
            logger.info("Phase 3: Computing completion rates for %d albums...", len(albums))
            stats.total_items = len(albums)
            stats.skipped = bulk_inserted - len(albums) if resume else 0
            
            updates = []
            for idx, row in enumerate(albums):
                album_id = row["album_id"]
                stats.current_item = idx + 1
                
                if progress_callback and idx % 500 == 0:
                    progress_callback(stats)

                try:
                    track_count = track_count_by_album.get(album_id, 0)
                    plays = plays_by_album.get(album_id, [])
                    completion_rate = self._calc_completion_rate(plays, track_count)
                    updates.append((completion_rate, album_id))
                    stats.albums_computed += 1
                except Exception as e:
                    stats.errors.append(f"Album {album_id}: {e}")

            # Batch update
            logger.info("Phase 4: Batch updating %d albums...", len(updates))
            db.executemany(
                "UPDATE album_analytics SET completion_rate = ? WHERE album_id = ?",
                updates,
            )

        self._log_computation("album_analytics", stats.albums_computed, "completed")
        return stats.to_dict()

    def _calc_completion_rate(self, plays: List[tuple], track_count: int) -> float:
        """Calculate completion rate from pre-fetched play data."""
        if track_count < 3 or len(plays) < track_count:
            return 0.0

        completion_count = 0
        session_tracks: set = set()
        last_time: Optional[datetime] = None

        for ts_str, track_id in plays:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if last_time and (ts - last_time).total_seconds() > 3600:
                if len(session_tracks) >= track_count * 0.8:
                    completion_count += 1
                session_tracks = set()
            session_tracks.add(track_id)
            last_time = ts

        if len(session_tracks) >= track_count * 0.8:
            completion_count += 1

        total_possible = len(plays) // track_count if track_count > 0 else 0
        return round(completion_count / max(total_possible, 1), 3)

    def compute_track_analytics(
        self, *, resume: bool = True, progress_callback: ProgressCallback = None
    ) -> Dict[str, Any]:
        """Compute analytics for all tracks with plays.
        
        Uses bulk SQL for all data, then computes is_sleeper in Python.
        
        Args:
            resume: If True, skip tracks that already have computed analytics.
            progress_callback: Optional callback for progress updates.
        """
        stats = AnalyticsStats()
        now_iso = datetime.now(UTC).isoformat()

        with connect(self.db_path) as db:
            if not resume:
                db.execute("DELETE FROM track_analytics")

            # PHASE 1: Bulk insert basic stats + time distribution
            logger.info("Phase 1: Bulk inserting track stats...")
            db.execute(
                """
                INSERT OR REPLACE INTO track_analytics 
                (track_id, first_play_date, last_play_date, total_plays, total_duration_ms,
                 morning_plays, afternoon_plays, evening_plays, night_plays, computed_at)
                SELECT 
                    p.canonical_track_id,
                    MIN(date(p.play_timestamp_utc)),
                    MAX(date(p.play_timestamp_utc)),
                    COUNT(*),
                    COALESCE(SUM(COALESCE(p.duration_ms, p.ms_played, 0)), 0),
                    SUM(CASE WHEN CAST(strftime('%H', p.play_timestamp_utc) AS INTEGER) BETWEEN 6 AND 11 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN CAST(strftime('%H', p.play_timestamp_utc) AS INTEGER) BETWEEN 12 AND 17 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN CAST(strftime('%H', p.play_timestamp_utc) AS INTEGER) BETWEEN 18 AND 21 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN CAST(strftime('%H', p.play_timestamp_utc) AS INTEGER) >= 22 
                             OR CAST(strftime('%H', p.play_timestamp_utc) AS INTEGER) < 6 THEN 1 ELSE 0 END),
                    ?
                FROM plays p
                WHERE p.canonical_track_id IS NOT NULL AND p.is_duplicate = 0
                GROUP BY p.canonical_track_id
                """,
                (now_iso,),
            )
            bulk_inserted = db.execute("SELECT changes()").fetchone()[0]
            logger.info("Bulk inserted %d track stats", bulk_inserted)

            # PHASE 2: Bulk fetch yearly plays for is_sleeper calculation
            logger.info("Phase 2: Bulk fetching yearly play data...")
            
            if resume:
                tracks = db.execute(
                    """
                    SELECT track_id, total_plays 
                    FROM track_analytics 
                    WHERE is_sleeper IS NULL AND total_plays >= 10
                    """
                ).fetchall()
            else:
                tracks = db.execute(
                    "SELECT track_id, total_plays FROM track_analytics WHERE total_plays >= 10"
                ).fetchall()
            
            track_ids = {row["track_id"] for row in tracks}
            
            # Bulk fetch: yearly plays per track
            logger.info("  Fetching yearly play counts...")
            yearly_rows = db.execute(
                """
                SELECT canonical_track_id, strftime('%Y', play_timestamp_utc) AS year, COUNT(*) AS plays
                FROM plays
                WHERE canonical_track_id IS NOT NULL AND is_duplicate = 0
                GROUP BY canonical_track_id, year
                """
            ).fetchall()
            yearly_by_track: Dict[int, List[int]] = {}
            for row in yearly_rows:
                tid = row["canonical_track_id"]
                if tid in track_ids:
                    yearly_by_track.setdefault(tid, []).append(row["plays"])

            # PHASE 3: Compute is_sleeper in Python
            logger.info("Phase 3: Computing is_sleeper for %d tracks...", len(tracks))
            stats.total_items = len(tracks)
            stats.skipped = bulk_inserted - len(tracks)
            
            updates = []
            for idx, row in enumerate(tracks):
                track_id = row["track_id"]
                stats.current_item = idx + 1
                
                if progress_callback and idx % 1000 == 0:
                    progress_callback(stats)

                try:
                    yearly = yearly_by_track.get(track_id, [])
                    is_sleeper = self._calc_is_sleeper(yearly)
                    updates.append((1 if is_sleeper else 0, track_id))
                    stats.tracks_computed += 1
                except Exception as e:
                    stats.errors.append(f"Track {track_id}: {e}")

            # Batch update
            logger.info("Phase 4: Batch updating %d tracks...", len(updates))
            db.executemany(
                "UPDATE track_analytics SET is_sleeper = ? WHERE track_id = ?",
                updates,
            )
            
            # Set is_sleeper = 0 for tracks with < 10 plays
            db.execute("UPDATE track_analytics SET is_sleeper = 0 WHERE is_sleeper IS NULL")

        self._log_computation("track_analytics", stats.tracks_computed, "completed")
        return stats.to_dict()

    def _calc_is_sleeper(self, yearly_plays: List[int]) -> bool:
        """Calculate is_sleeper from pre-fetched yearly play counts."""
        if len(yearly_plays) < 2:
            return False
        max_plays = max(yearly_plays)
        avg_plays = sum(yearly_plays) / len(yearly_plays)
        return max_plays < avg_plays * 2.5 and all(p >= avg_plays * 0.3 for p in yearly_plays)

    def compute_temporal_analytics(self) -> Dict[str, Any]:
        """Compute monthly, hourly, and weekday distributions."""
        stats = AnalyticsStats()
        now_iso = datetime.now(UTC).isoformat()

        with connect(self.db_path) as db:
            stats.monthly_periods = self._compute_monthly_summary(db, now_iso)
            self._compute_hourly_distribution(db, now_iso)
            self._compute_weekday_distribution(db, now_iso)

        self._log_computation("temporal_analytics", stats.monthly_periods, "completed")
        return stats.to_dict()

    def _compute_monthly_summary(self, db, now_iso: str) -> int:
        # Bulk fetch: basic monthly stats
        months = db.execute(
            """
            SELECT
                strftime('%Y-%m', play_timestamp_utc) AS year_month,
                COUNT(*) AS total_plays,
                COALESCE(SUM(COALESCE(duration_ms, ms_played, 0)), 0) AS total_duration_ms,
                COUNT(DISTINCT primary_artist_id) AS unique_artists,
                COUNT(DISTINCT canonical_album_id) AS unique_albums,
                COUNT(DISTINCT canonical_track_id) AS unique_tracks
            FROM plays
            WHERE is_duplicate = 0
            GROUP BY year_month
            ORDER BY year_month
            """
        ).fetchall()

        # Bulk fetch: artists per month (for new_artists calculation)
        artists_by_month_rows = db.execute(
            """
            SELECT strftime('%Y-%m', play_timestamp_utc) AS year_month, primary_artist_id
            FROM plays
            WHERE is_duplicate = 0 AND primary_artist_id IS NOT NULL
            GROUP BY year_month, primary_artist_id
            ORDER BY year_month
            """
        ).fetchall()
        artists_by_month: Dict[str, set] = {}
        for row in artists_by_month_rows:
            artists_by_month.setdefault(row["year_month"], set()).add(row["primary_artist_id"])

        # Bulk fetch: top artist per month
        top_artist_rows = db.execute(
            """
            SELECT year_month, primary_artist_id, plays FROM (
                SELECT 
                    strftime('%Y-%m', play_timestamp_utc) AS year_month,
                    primary_artist_id,
                    COUNT(*) AS plays,
                    ROW_NUMBER() OVER (PARTITION BY strftime('%Y-%m', play_timestamp_utc) ORDER BY COUNT(*) DESC) AS rn
                FROM plays
                WHERE is_duplicate = 0 AND primary_artist_id IS NOT NULL
                GROUP BY year_month, primary_artist_id
            ) WHERE rn = 1
            """
        ).fetchall()
        top_artist_by_month = {row["year_month"]: (row["primary_artist_id"], row["plays"]) for row in top_artist_rows}

        # Compute new_artists per month (cumulative tracking)
        seen_artists: set = set()
        updates = []

        for row in months:
            ym = row["year_month"]
            month_artists = artists_by_month.get(ym, set())
            new_artists = len(month_artists - seen_artists)
            seen_artists.update(month_artists)

            top = top_artist_by_month.get(ym)
            frag_score = row["unique_artists"] / row["total_plays"] if row["total_plays"] > 0 else 0

            updates.append((
                ym,
                row["total_plays"],
                row["total_duration_ms"],
                row["unique_artists"],
                row["unique_albums"],
                row["unique_tracks"],
                new_artists,
                top[0] if top else None,
                top[1] if top else None,
                round(frag_score, 4),
                now_iso,
            ))

        db.executemany(
            """
            INSERT OR REPLACE INTO monthly_summary
            (year_month, total_plays, total_duration_ms, unique_artists, unique_albums,
             unique_tracks, new_artists_discovered, top_artist_id, top_artist_plays,
             fragmentation_score, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            updates,
        )

        return len(updates)

    def _compute_hourly_distribution(self, db, now_iso: str) -> None:
        total_days = db.execute(
            "SELECT COUNT(DISTINCT date(play_timestamp_utc)) AS c FROM plays WHERE is_duplicate = 0"
        ).fetchone()["c"]

        hours = db.execute(
            """
            SELECT
                CAST(strftime('%H', play_timestamp_utc) AS INTEGER) AS hour,
                COUNT(*) AS total_plays
            FROM plays
            WHERE is_duplicate = 0
            GROUP BY hour
            """
        ).fetchall()

        for row in hours:
            avg_per_day = row["total_plays"] / total_days if total_days > 0 else 0
            db.execute(
                """
                INSERT OR REPLACE INTO hourly_distribution (hour, total_plays, avg_plays_per_day, computed_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["hour"], row["total_plays"], round(avg_per_day, 3), now_iso),
            )

    def _compute_weekday_distribution(self, db, now_iso: str) -> None:
        total_weeks = db.execute(
            """
            SELECT COUNT(DISTINCT strftime('%Y-%W', play_timestamp_utc)) AS c
            FROM plays WHERE is_duplicate = 0
            """
        ).fetchone()["c"]

        weekdays = db.execute(
            """
            SELECT
                CAST(strftime('%w', play_timestamp_utc) AS INTEGER) AS weekday,
                COUNT(*) AS total_plays
            FROM plays
            WHERE is_duplicate = 0
            GROUP BY weekday
            """
        ).fetchall()

        for row in weekdays:
            avg_per_week = row["total_plays"] / total_weeks if total_weeks > 0 else 0
            db.execute(
                """
                INSERT OR REPLACE INTO weekday_distribution (weekday, total_plays, avg_plays_per_week, computed_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["weekday"], row["total_plays"], round(avg_per_week, 3), now_iso),
            )

    def compute_discovery_context(self) -> Dict[str, Any]:
        """Compute gateway artist relationships."""
        stats = AnalyticsStats()
        now_iso = datetime.now(UTC).isoformat()

        with connect(self.db_path) as db:
            logger.info("Computing discovery context with bulk queries...")
            
            # Get all artists with first play dates
            artists = db.execute(
                """
                SELECT artist_id, first_play_date
                FROM artist_analytics
                WHERE first_play_date IS NOT NULL
                """
            ).fetchall()
            
            # Bulk fetch: all plays by date and artist (for context lookup)
            logger.info("  Fetching daily artist play counts...")
            daily_plays = db.execute(
                """
                SELECT date(play_timestamp_utc) AS play_date, primary_artist_id, COUNT(*) AS plays
                FROM plays
                WHERE is_duplicate = 0 AND primary_artist_id IS NOT NULL
                GROUP BY play_date, primary_artist_id
                """
            ).fetchall()
            
            # Build index: date -> [(artist_id, plays), ...]
            plays_by_date: Dict[str, List[tuple]] = {}
            for row in daily_plays:
                plays_by_date.setdefault(row["play_date"], []).append(
                    (row["primary_artist_id"], row["plays"])
                )
            
            # Compute context for each artist
            logger.info("  Computing context for %d artists...", len(artists))
            inserts = []
            
            for artist in artists:
                artist_id = artist["artist_id"]
                first_play = artist["first_play_date"]
                first_date = datetime.fromisoformat(first_play).date()
                
                # Aggregate plays in week before
                context_before: Dict[int, int] = {}
                for i in range(1, 8):
                    d = (first_date - timedelta(days=i)).isoformat()
                    for aid, plays in plays_by_date.get(d, []):
                        if aid != artist_id:
                            context_before[aid] = context_before.get(aid, 0) + plays
                
                # Aggregate plays in week after (including first day)
                context_after: Dict[int, int] = {}
                for i in range(8):
                    d = (first_date + timedelta(days=i)).isoformat()
                    for aid, plays in plays_by_date.get(d, []):
                        if aid != artist_id:
                            context_after[aid] = context_after.get(aid, 0) + plays
                
                # Top 5 before
                top_before = sorted(context_before.items(), key=lambda x: -x[1])[:5]
                for ctx_artist, plays in top_before:
                    inserts.append((artist_id, ctx_artist, 'before', plays, now_iso))
                    stats.discovery_links += 1
                
                # Top 5 after
                top_after = sorted(context_after.items(), key=lambda x: -x[1])[:5]
                for ctx_artist, plays in top_after:
                    inserts.append((artist_id, ctx_artist, 'after', plays, now_iso))
                    stats.discovery_links += 1

            # Batch insert
            logger.info("  Batch inserting %d discovery links...", len(inserts))
            db.execute("DELETE FROM discovery_context")
            db.executemany(
                """
                INSERT INTO discovery_context
                (discovered_artist_id, context_artist_id, context_type, play_count, computed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                inserts,
            )

        self._log_computation("discovery_context", stats.discovery_links, "completed")
        return stats.to_dict()

    def compute_geographic_analytics(self) -> Dict[str, Any]:
        """Compute geographic listening patterns."""
        now_iso = datetime.now(UTC).isoformat()

        with connect(self.db_path) as db:
            geo = db.execute(
                """
                SELECT
                    location_country,
                    location_region,
                    location_city,
                    COUNT(*) AS total_plays,
                    MIN(date(play_timestamp_utc)) AS first_play_date,
                    MAX(date(play_timestamp_utc)) AS last_play_date
                FROM plays
                WHERE location_country IS NOT NULL AND is_duplicate = 0
                GROUP BY location_country, location_region, location_city
                """
            ).fetchall()

            updates = [
                (
                    row["location_country"],
                    row["location_region"],
                    row["location_city"],
                    row["total_plays"],
                    row["first_play_date"],
                    row["last_play_date"],
                    now_iso,
                )
                for row in geo
            ]
            
            db.executemany(
                """
                INSERT OR REPLACE INTO geographic_analytics
                (country, region, city, total_plays, first_play_date, last_play_date, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                updates,
            )

        self._log_computation("geographic_analytics", len(geo), "completed")
        return {"locations_computed": len(geo)}

    def compute_all(self, *, resume: bool = True) -> Dict[str, Any]:
        """Run full analytics computation pipeline.
        
        Args:
            resume: If True, skip entities that already have computed analytics.
        """
        results = {}
        results["artists"] = self.compute_artist_analytics(resume=resume)
        results["albums"] = self.compute_album_analytics(resume=resume)
        results["tracks"] = self.compute_track_analytics(resume=resume)
        results["temporal"] = self.compute_temporal_analytics()
        results["discovery"] = self.compute_discovery_context()
        results["geographic"] = self.compute_geographic_analytics()
        return results

    def summary(self) -> Dict[str, Any]:
        """Return high-level analytics summary."""
        with connect(self.db_path) as db:
            total_plays = db.execute(
                "SELECT COUNT(*) AS c FROM plays WHERE is_duplicate = 0"
            ).fetchone()["c"]

            total_duration = db.execute(
                "SELECT COALESCE(SUM(COALESCE(duration_ms, ms_played, 0)), 0) AS d FROM plays WHERE is_duplicate = 0"
            ).fetchone()["d"]

            unique_artists = db.execute(
                "SELECT COUNT(DISTINCT primary_artist_id) AS c FROM plays WHERE is_duplicate = 0"
            ).fetchone()["c"]

            unique_albums = db.execute(
                "SELECT COUNT(DISTINCT canonical_album_id) AS c FROM plays WHERE is_duplicate = 0"
            ).fetchone()["c"]

            unique_tracks = db.execute(
                "SELECT COUNT(DISTINCT canonical_track_id) AS c FROM plays WHERE is_duplicate = 0"
            ).fetchone()["c"]

            date_range = db.execute(
                """
                SELECT MIN(date(play_timestamp_utc)) AS first, MAX(date(play_timestamp_utc)) AS last
                FROM plays WHERE is_duplicate = 0
                """
            ).fetchone()

            top_artists = db.execute(
                """
                SELECT ca.name, aa.total_plays, aa.loyalty_tier
                FROM artist_analytics aa
                JOIN canonical_artists ca ON ca.id = aa.artist_id
                ORDER BY aa.total_plays DESC
                LIMIT 10
                """
            ).fetchall()

            loyalty_dist = db.execute(
                """
                SELECT loyalty_tier, COUNT(*) AS c
                FROM artist_analytics
                WHERE loyalty_tier IS NOT NULL
                GROUP BY loyalty_tier
                """
            ).fetchall()

            ghost_artists = db.execute(
                """
                SELECT COUNT(*) AS c FROM artist_analytics
                WHERE days_since_last_play > 365 AND total_plays >= 10
                """
            ).fetchone()["c"]

            sleeper_tracks = db.execute(
                "SELECT COUNT(*) AS c FROM track_analytics WHERE is_sleeper = 1"
            ).fetchone()["c"]

        hours_listened = total_duration / (1000 * 60 * 60) if total_duration else 0

        return {
            "overview": {
                "total_plays": total_plays,
                "total_hours_listened": round(hours_listened, 1),
                "unique_artists": unique_artists,
                "unique_albums": unique_albums,
                "unique_tracks": unique_tracks,
                "date_range": {
                    "first": date_range["first"],
                    "last": date_range["last"],
                },
            },
            "top_artists": [
                {"name": a["name"], "plays": a["total_plays"], "tier": a["loyalty_tier"]}
                for a in top_artists
            ],
            "loyalty_distribution": {r["loyalty_tier"]: r["c"] for r in loyalty_dist},
            "insights": {
                "ghost_artists": ghost_artists,
                "sleeper_tracks": sleeper_tracks,
            },
        }

    def export_json(self, output_dir: Path) -> Dict[str, str]:
        """Export pre-computed analytics as JSON files for dashboard."""
        output_dir.mkdir(parents=True, exist_ok=True)
        exported = {}

        summary = self.summary()
        summary_path = output_dir / "summary.json"
        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2)
        exported["summary"] = str(summary_path)

        with connect(self.db_path) as db:
            monthly = db.execute(
                "SELECT * FROM monthly_summary ORDER BY year_month"
            ).fetchall()
            monthly_path = output_dir / "monthly.json"
            with monthly_path.open("w") as f:
                json.dump([dict(r) for r in monthly], f, indent=2)
            exported["monthly"] = str(monthly_path)

            hourly = db.execute(
                "SELECT * FROM hourly_distribution ORDER BY hour"
            ).fetchall()
            hourly_path = output_dir / "hourly.json"
            with hourly_path.open("w") as f:
                json.dump([dict(r) for r in hourly], f, indent=2)
            exported["hourly"] = str(hourly_path)

            weekday = db.execute(
                "SELECT * FROM weekday_distribution ORDER BY weekday"
            ).fetchall()
            weekday_path = output_dir / "weekday.json"
            with weekday_path.open("w") as f:
                json.dump([dict(r) for r in weekday], f, indent=2)
            exported["weekday"] = str(weekday_path)

            top_artists = db.execute(
                """
                SELECT aa.*, ca.name AS artist_name
                FROM artist_analytics aa
                JOIN canonical_artists ca ON ca.id = aa.artist_id
                ORDER BY aa.total_plays DESC
                LIMIT 100
                """
            ).fetchall()
            artists_path = output_dir / "top_artists.json"
            with artists_path.open("w") as f:
                json.dump([dict(r) for r in top_artists], f, indent=2)
            exported["top_artists"] = str(artists_path)

            geographic = db.execute(
                "SELECT * FROM geographic_analytics ORDER BY total_plays DESC"
            ).fetchall()
            if geographic:
                geo_path = output_dir / "geographic.json"
                with geo_path.open("w") as f:
                    json.dump([dict(r) for r in geographic], f, indent=2)
                exported["geographic"] = str(geo_path)

        return exported
