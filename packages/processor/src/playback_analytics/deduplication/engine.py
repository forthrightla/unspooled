"""Cross-source deduplication engine for normalized plays."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from rapidfuzz import fuzz

from playback_analytics.config import Settings
from playback_analytics.db import connect

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DeduplicationStats:
    plays_considered: int = 0
    pairs_scored: int = 0
    duplicates_merged: int = 0
    flagged_for_review: int = 0
    merge_winners: Dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.merge_winners is None:
            self.merge_winners = defaultdict(int)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plays_considered": self.plays_considered,
            "pairs_scored": self.pairs_scored,
            "duplicates_merged": self.duplicates_merged,
            "flagged_for_review": self.flagged_for_review,
            "merge_winners": dict(self.merge_winners),
        }


class DeduplicationEngine:
    """Identify duplicate plays across different data sources."""

    SOURCE_PRIORITY = {
        "spotify": 4,
        "apple_music": 3,
        "lastfm": 2,
        "manual": 1,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.paths.database_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        *,
        window_seconds: int = 60,
        fuzzy_threshold: float = 0.9,
        duration_tolerance: float = 0.10,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a deduplication pass and return summary stats."""

        stats = DeduplicationStats()
        plays = self._load_candidate_plays()
        stats.plays_considered = len(plays)
        if not plays:
            logger.info("No plays available for deduplication.")
            return stats.to_dict()

        auto_merges: List[Dict[str, Any]] = []
        review_pairs: List[Dict[str, Any]] = []
        pairs_seen: set[Tuple[int, int]] = set()
        max_pair_window = max(window_seconds, 120)

        grouped: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
        for play in plays:
            key = (play["canonical_track_id"], play["primary_artist_id"])
            if None in key:
                continue
            grouped[key].append(play)

        for rows in grouped.values():
            rows.sort(key=lambda row: row["played_at"])
            for idx, current in enumerate(rows):
                for other in rows[idx + 1 :]:
                    if current["source_name"] == other["source_name"]:
                        continue
                    time_diff = abs((current["played_at"] - other["played_at"]).total_seconds())
                    if time_diff > max_pair_window:
                        break
                    pair_key = tuple(sorted((current["id"], other["id"])))
                    if pair_key in pairs_seen:
                        continue
                    pairs_seen.add(pair_key)
                    score, detail = self._score_pair(
                        current,
                        other,
                        time_diff=time_diff,
                        window_seconds=window_seconds,
                        fuzzy_threshold=fuzzy_threshold,
                        duration_tolerance=duration_tolerance,
                    )
                    if score == 0:
                        continue
                    candidate = {
                        "a_id": current["id"],
                        "b_id": other["id"],
                        "score": score,
                        "reason": detail,
                        "time_diff": time_diff,
                    }
                    stats.pairs_scored += 1
                    if score >= 70:
                        auto_merges.append(candidate)
                    elif 50 <= score < 70:
                        review_pairs.append(candidate)

        if not auto_merges and not review_pairs:
            logger.info("No duplicate pairs detected (window=%ss).", window_seconds)
            return stats.to_dict()

        parent = {play["id"]: play["id"] for play in plays}
        merge_meta: Dict[int, Dict[str, Any]] = {}
        play_lookup = {play["id"]: play for play in plays}

        auto_merges.sort(key=lambda item: (item["score"], -item["time_diff"]), reverse=True)

        for candidate in auto_merges:
            root_a = self._find(parent, candidate["a_id"])
            root_b = self._find(parent, candidate["b_id"])
            if root_a == root_b:
                continue
            winner_id, loser_id = self._choose_winner(play_lookup[root_a], play_lookup[root_b])
            parent[self._find(parent, loser_id)] = self._find(parent, winner_id)
            merge_meta[loser_id] = {
                "score": candidate["score"],
                "reason": candidate["reason"],
                "matched_with": winner_id,
            }
            stats.duplicates_merged += 1
            stats.merge_winners[play_lookup[winner_id]["source_name"]] += 1

        if review_pairs and not dry_run:
            self._reset_pending_reviews()
            self._store_review_pairs(review_pairs)
            stats.flagged_for_review = len(review_pairs)
        elif review_pairs:
            stats.flagged_for_review = len(review_pairs)

        if dry_run:
            return stats.to_dict()

        self._apply_merges(parent, merge_meta, play_lookup)
        logger.info(
            "Deduplication finished (merged=%s, review=%s)",
            stats.duplicates_merged,
            stats.flagged_for_review,
        )
        return stats.to_dict()

    def report(self) -> Dict[str, Any]:
        """Return high-level deduplication metrics."""
        with connect(self.db_path) as db:
            total = db.execute("SELECT COUNT(*) AS c FROM plays").fetchone()["c"]
            duplicates = db.execute(
                "SELECT COUNT(*) AS c FROM plays WHERE is_duplicate = 1"
            ).fetchone()["c"]
            flagged = db.execute(
                "SELECT COUNT(*) AS c FROM dedupe_review_queue WHERE resolved = 0"
            ).fetchone()["c"]
            by_source = db.execute(
                """
                SELECT dedupe_winner_source AS source, COUNT(*) AS c
                FROM plays
                WHERE is_duplicate = 1 AND dedupe_winner_source IS NOT NULL
                GROUP BY dedupe_winner_source
                """
            ).fetchall()
            return {
                "total_plays": total,
                "duplicates_marked": duplicates,
                "flagged_for_review": flagged,
                "merge_winners": {row["source"]: row["c"] for row in by_source},
            }

    def export_review(self, output_path: Path) -> None:
        """Export unresolved review queue entries for manual triage."""
        with connect(self.db_path) as db:
            rows = db.execute(
                """
                SELECT
                    q.id,
                    q.play_a_id,
                    q.play_b_id,
                    q.confidence,
                    q.reason,
                    pa.source_name AS play_a_source,
                    pa.play_timestamp_utc AS play_a_timestamp,
                    pa.duration_ms AS play_a_duration,
                    pb.source_name AS play_b_source,
                    pb.play_timestamp_utc AS play_b_timestamp,
                    pb.duration_ms AS play_b_duration
                FROM dedupe_review_queue q
                JOIN plays pa ON pa.id = q.play_a_id
                JOIN plays pb ON pb.id = q.play_b_id
                WHERE q.resolved = 0
                ORDER BY q.confidence DESC, q.created_at ASC
                """
            ).fetchall()

        if not rows:
            logger.info("No pending dedupe review entries to export.")
            return

        export_data = {
            "generated_at": datetime.now(UTC).isoformat(),
            "pending": [
                {
                    "id": row["id"],
                    "score": row["confidence"],
                    "reason": row["reason"],
                    "play_a": {
                        "id": row["play_a_id"],
                        "source": row["play_a_source"],
                        "timestamp": row["play_a_timestamp"],
                        "duration_ms": row["play_a_duration"],
                    },
                    "play_b": {
                        "id": row["play_b_id"],
                        "source": row["play_b_source"],
                        "timestamp": row["play_b_timestamp"],
                        "duration_ms": row["play_b_duration"],
                    },
                }
                for row in rows
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(export_data, handle, sort_keys=False)
        logger.info("Exported %s review entries to %s", len(rows), output_path)

    def undo(self) -> Dict[str, int]:
        """Clear deduplication markers so the process can be re-run."""
        with connect(self.db_path) as db:
            updated = db.execute(
                """
                UPDATE plays
                SET is_duplicate = 0,
                    duplicate_of_id = NULL,
                    dedupe_confidence = NULL,
                    dedupe_notes = NULL,
                    dedupe_winner_source = NULL,
                    deduped_at = NULL
                WHERE is_duplicate = 1 OR duplicate_of_id IS NOT NULL
                """
            ).rowcount
            db.execute("DELETE FROM dedupe_review_queue")
        logger.info("Reset dedupe flags on %s plays", updated)
        return {"plays_reset": updated}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_candidate_plays(self) -> List[Dict[str, Any]]:
        with connect(self.db_path) as db:
            rows = db.execute(
                """
                SELECT
                    p.id,
                    p.canonical_track_id,
                    p.primary_artist_id,
                    p.canonical_album_id,
                    p.play_timestamp_utc,
                    p.duration_ms,
                    p.ms_played,
                    p.source_name,
                    p.source_record_id,
                    p.source_row_table,
                    p.is_duplicate,
                    p.dedupe_confidence,
                    ct.title AS canonical_track_title
                FROM plays p
                LEFT JOIN canonical_tracks ct ON ct.id = p.canonical_track_id
                WHERE p.canonical_track_id IS NOT NULL
                  AND p.primary_artist_id IS NOT NULL
                ORDER BY p.play_timestamp_utc ASC
                """
            ).fetchall()

        plays: List[Dict[str, Any]] = []
        for row in rows:
            timestamp = self._parse_timestamp(row["play_timestamp_utc"])
            plays.append(
                {
                    "id": row["id"],
                    "canonical_track_id": row["canonical_track_id"],
                    "primary_artist_id": row["primary_artist_id"],
                    "canonical_album_id": row["canonical_album_id"],
                    "played_at": timestamp,
                    "duration_ms": row["duration_ms"],
                    "ms_played": row["ms_played"],
                    "source_name": row["source_name"],
                    "source_record_id": row["source_record_id"],
                    "source_row_table": row["source_row_table"],
                    "track_title": row["canonical_track_title"],
                }
            )
        return plays

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone(UTC)

    def _score_pair(
        self,
        play_a: Dict[str, Any],
        play_b: Dict[str, Any],
        *,
        time_diff: float,
        window_seconds: int,
        fuzzy_threshold: float,
        duration_tolerance: float,
    ) -> Tuple[int, str]:
        if play_a["primary_artist_id"] != play_b["primary_artist_id"]:
            return 0, "artist_mismatch"

        score = 0
        details: List[str] = []

        if time_diff == 0:
            score += 50
            details.append("exact_timestamp")
        elif time_diff <= 30:
            score += 40
            details.append("within_30s")
        elif time_diff <= window_seconds:
            score += 30
            details.append(f"within_{window_seconds}s")
        elif time_diff <= 120:
            score += 20
            details.append("within_120s")
        else:
            return 0, "time_window_exceeded"

        if play_a["canonical_track_id"] == play_b["canonical_track_id"]:
            score += 30
            details.append("same_canonical_track")
        else:
            similarity = self._track_similarity(play_a, play_b)
            if similarity >= fuzzy_threshold:
                score += 20
                details.append(f"fuzzy_track_{similarity:.2f}")
            else:
                return 0, "track_mismatch"

        if (
            play_a.get("canonical_album_id")
            and play_a["canonical_album_id"] == play_b.get("canonical_album_id")
        ):
            score += 10
            details.append("same_album")

        if self._duration_similar(play_a, play_b, tolerance=duration_tolerance):
            score += 10
            details.append("duration_match")

        return score, ", ".join(details)

    @staticmethod
    def _track_similarity(play_a: Dict[str, Any], play_b: Dict[str, Any]) -> float:
        title_a = play_a.get("track_title") or ""
        title_b = play_b.get("track_title") or ""
        if not title_a or not title_b:
            return 0.0
        return fuzz.ratio(title_a, title_b) / 100.0

    @staticmethod
    def _duration_similar(
        play_a: Dict[str, Any], play_b: Dict[str, Any], *, tolerance: float
    ) -> bool:
        a_duration = play_a.get("duration_ms") or play_a.get("ms_played")
        b_duration = play_b.get("duration_ms") or play_b.get("ms_played")
        if not a_duration or not b_duration:
            return False
        difference = abs(a_duration - b_duration)
        allowed = max(a_duration, b_duration) * tolerance
        return difference <= allowed

    def _choose_winner(
        self, play_a: Dict[str, Any], play_b: Dict[str, Any]
    ) -> Tuple[int, int]:
        score_a = self.SOURCE_PRIORITY.get(play_a["source_name"], 0)
        score_b = self.SOURCE_PRIORITY.get(play_b["source_name"], 0)
        if score_a > score_b:
            return play_a["id"], play_b["id"]
        if score_b > score_a:
            return play_b["id"], play_a["id"]

        # Tie-breaker: prefer play with explicit duration, then earliest timestamp, then lower id
        has_duration_a = 1 if (play_a.get("duration_ms") or play_a.get("ms_played")) else 0
        has_duration_b = 1 if (play_b.get("duration_ms") or play_b.get("ms_played")) else 0
        if has_duration_a > has_duration_b:
            return play_a["id"], play_b["id"]
        if has_duration_b > has_duration_a:
            return play_b["id"], play_a["id"]

        if play_a["played_at"] <= play_b["played_at"]:
            return play_a["id"], play_b["id"]
        return play_b["id"], play_a["id"]

    def _apply_merges(
        self,
        parent: Dict[int, int],
        merge_meta: Dict[int, Dict[str, Any]],
        play_lookup: Dict[int, Dict[str, Any]],
    ) -> None:
        updates: List[Tuple[int, Optional[int], Optional[int], Optional[str], Optional[str]]] = []
        now = datetime.now(UTC).isoformat()

        for play_id in sorted(parent.keys()):
            root_id = self._find(parent, play_id)
            if root_id == play_id:
                continue
            meta = merge_meta.get(play_id)
            if meta is None:
                # The play was part of a cluster that lost later; reuse the root meta
                meta = merge_meta.get(root_id)
            if meta is None:
                logger.debug("Missing merge metadata for play_id=%s", play_id)
                continue
            winner_source = play_lookup[self._find(parent, root_id)]["source_name"]
            updates.append(
                (
                    root_id,
                    meta.get("score"),
                    winner_source,
                    meta.get("reason"),
                    play_id,
                )
            )

        if not updates:
            return

        with connect(self.db_path) as db:
            db.executemany(
                """
                UPDATE plays
                SET is_duplicate = 1,
                    duplicate_of_id = ?,
                    dedupe_confidence = ?,
                    dedupe_winner_source = ?,
                    dedupe_notes = ?,
                    deduped_at = ?
                WHERE id = ?
                """,
                [
                    (winner_id, score, winner_source, notes, now, play_id)
                    for (winner_id, score, winner_source, notes, play_id) in updates
                ],
            )

    def _reset_pending_reviews(self) -> None:
        with connect(self.db_path) as db:
            db.execute("DELETE FROM dedupe_review_queue WHERE resolved = 0")

    def _store_review_pairs(self, review_pairs: List[Dict[str, Any]]) -> None:
        if not review_pairs:
            return
        records = []
        for pair in review_pairs:
            a_id, b_id = sorted((pair["a_id"], pair["b_id"]))
            records.append((a_id, b_id, pair["score"], pair["reason"]))
        with connect(self.db_path) as db:
            db.executemany(
                """
                INSERT INTO dedupe_review_queue (play_a_id, play_b_id, confidence, reason)
                VALUES (?, ?, ?, ?)
                """,
                records,
            )

    @staticmethod
    def _find(parent: Dict[int, int], play_id: int) -> int:
        root = play_id
        while parent[root] != root:
            root = parent[root]
        # Path compression
        while parent[play_id] != play_id:
            parent_play = parent[play_id]
            parent[play_id] = root
            play_id = parent_play
        return root
