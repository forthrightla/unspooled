"""Core normalization engine for canonical entity resolution."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from phonetics import metaphone
from rapidfuzz import fuzz, process
from unidecode import unidecode

from playback_analytics.config import Settings
from playback_analytics.db import DatabaseSession, connect
from playback_analytics.normalization.utils import (
    normalize_artist_name,
    slugify_value,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizationMatch:
    canonical_id: int
    canonical_name: str
    confidence: float
    method: str
    notes: Optional[str] = None


class NormalizationEngine:
    """Handles clustering and canonicalization of music metadata."""

    # Regex patterns for featuring artist extraction
    FEAT_PATTERNS = [
        re.compile(r"\(feat\.?\s+(.*?)\)", re.I),
        re.compile(r"\(featuring\s+(.*?)\)", re.I),
        re.compile(r"\(with\s+(.*?)\)", re.I),
        re.compile(r"\[ft\.?\s+(.*?)\]", re.I),
        re.compile(r"\[featuring\s+(.*?)\]", re.I),
        re.compile(r"featuring\s+(.+)$", re.I),
        re.compile(r"feat\.?\s+(.+)$", re.I),
    ]
    
    # Regex patterns for collaboration splitting
    # NOTE: Comma pattern removed - too aggressive (breaks "Earth, Wind & Fire")
    # Commas should be handled via manual overrides for specific cases
    COLLABORATION_PATTERNS = [
        re.compile(r"\s+&\s+"),
        re.compile(r"\s+and\s+", re.I),
        re.compile(r"\s+x\s+", re.I),
        re.compile(r"\s+vs\.?\s+", re.I),
    ]

    # Regex patterns for album cleaning (deluxe, remaster, etc.)
    ALBUM_CLEAN_PATTERNS = [
        re.compile(r"\s*\(.*?deluxe.*?\)", re.I),
        re.compile(r"\s*\(.*?remaster.*?\)", re.I),
        re.compile(r"\s*\(.*?reissue.*?\)", re.I),
        re.compile(r"\s*\(.*?anniversary.*?\)", re.I),
        re.compile(r"\s*\(.*?expanded.*?\)", re.I),
        re.compile(r"\s*\(.*?special.*?edition.*?\)", re.I),
        re.compile(r"\s*\(.*?collector.*?\)", re.I),
        re.compile(r"\s*\(.*?limited.*?edition.*?\)", re.I),
        re.compile(r"\s*\(.*?super.*?deluxe.*?\)", re.I),
        re.compile(r"\s*\[.*?uk.*?\]", re.I),
        re.compile(r"\s*\[.*?us.*?\]", re.I),
        re.compile(r"\s*\[.*?japan.*?\]", re.I),
        re.compile(r"\s*\[.*?bonus.*?\]", re.I),
        re.compile(r"\s*-\s*Single$", re.I),
        re.compile(r"\s*\(EP\)$", re.I),
    ]

    # Regex patterns for track parenthetical removal (for matching)
    # NOTE: Remixes are intentionally NOT removed - they are distinct works
    TRACK_CLEAN_PATTERNS = [
        re.compile(r"\s*\(.*?radio.*?edit.*?\)", re.I),
        re.compile(r"\s*\(.*?album.*?version.*?\)", re.I),
        re.compile(r"\s*\(.*?single.*?version.*?\)", re.I),
        re.compile(r"\s*\(.*?original.*?mix.*?\)", re.I),
        re.compile(r"\s*\(.*?instrumental.*?\)", re.I),
        re.compile(r"\s*\(.*?acoustic.*?\)", re.I),
        re.compile(r"\s*\(.*?demo.*?\)", re.I),
        re.compile(r"\s*\(.*?bonus.*?track.*?\)", re.I),
        re.compile(r"\s*-\s*\d{4}\s*Remaster(ed)?$", re.I),
        re.compile(r"\s*-\s*Remaster(ed)?$", re.I),
    ]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.paths.database_path
        self.overrides_path = Path(settings.paths.raw_spotify_history).parent / "normalization_overrides.yaml"
        self.overrides: Dict[str, Dict[str, Any]] = {}
        self.ambiguous_matches: List[Dict[str, Any]] = []
        self._load_overrides()

    def _load_overrides(self) -> None:
        """Load manual overrides from YAML file if it exists."""
        if not self.overrides_path.exists():
            return
            
        try:
            with self.overrides_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if data and isinstance(data, dict):
                    self.overrides = data
                    logger.info("Loaded normalization overrides from %s", self.overrides_path)
        except Exception as exc:
            logger.error("Failed to load normalization overrides: %s", exc)

    def normalize_case(self, text: str) -> str:
        """Apply case normalization: ALLCAPS -> Title Case, otherwise preserve."""
        if not text:
            return text
        if text.isupper() and len(text) > 2:
            return text.title()
        return text

    def normalize_artist_name_advanced(self, name: str) -> List[str]:
        """
        Advanced artist name normalization with collaboration splitting.
        Returns list of individual artist names for Option B approach.
        """
        if not name:
            return []

        # Check for manual override first
        if "artists" in self.overrides and name in self.overrides["artists"]:
            override = self.overrides["artists"][name]
            if isinstance(override, list):
                return override
            return [override]

        # Basic normalization
        clean_name = normalize_artist_name(name)
        if not clean_name:
            return []

        clean_name = self.normalize_case(clean_name)

        # Handle "The" prefix - we'll keep it but normalize for matching
        # "The National" stays "The National" but matches against "national"

        # Split collaborations into individual artists
        artists = self._split_collaborations(clean_name)
        
        return [a.strip() for a in artists if a.strip()]

    def _split_collaborations(self, artist_name: str) -> List[str]:
        """Split collaboration strings like 'Artist A & Artist B' into individual artists."""
        parts = [artist_name]
        
        for pattern in self.COLLABORATION_PATTERNS:
            new_parts = []
            for part in parts:
                split_parts = pattern.split(part)
                new_parts.extend(split_parts)
            parts = new_parts
            
        return [p.strip() for p in parts if p.strip()]

    def extract_featured_artists(self, track_name: str) -> Tuple[str, List[str], bool]:
        """
        Extract featured artists from track name.
        Returns (clean_track_name, featured_artists, is_live).
        """
        if not track_name:
            return "", [], False

        clean_track = track_name
        featured_artists = []
        # More precise live detection to avoid false positives like "Live Your Life"
        is_live = bool(re.search(r"\b(live|\blive\b.*?\bat\b|\blive\b.*?\bfrom\b|\blive\b.*?\bin\b)", track_name, re.I))

        # Extract featuring patterns
        for pattern in self.FEAT_PATTERNS:
            match = pattern.search(clean_track)
            if match:
                feat_text = match.group(1)
                # Split featured artists in case there are multiple
                feat_list = self._split_collaborations(feat_text)
                featured_artists.extend(feat_list)
                # Remove the featuring part from the track name
                clean_track = pattern.sub("", clean_track).strip()

        # Clean up empty parentheses/brackets
        clean_track = re.sub(r"\(\s*\)", "", clean_track).strip()
        clean_track = re.sub(r"\[\s*\]", "", clean_track).strip()
        
        return clean_track, featured_artists, is_live

    def canonicalize_album_name(self, album_name: str) -> str:
        """Remove deluxe/remaster/regional suffixes for canonical matching."""
        if not album_name:
            return ""

        # Check for manual override
        if "albums" in self.overrides and album_name in self.overrides["albums"]:
            return self.overrides["albums"][album_name]

        clean = album_name
        for pattern in self.ALBUM_CLEAN_PATTERNS:
            clean = pattern.sub("", clean).strip()
        
        return self.normalize_case(clean)

    def canonicalize_track_name(self, track_name: str) -> str:
        """Remove parentheticals for canonical matching while preserving core title."""
        if not track_name:
            return ""

        # Check for manual override
        if "tracks" in self.overrides and track_name in self.overrides["tracks"]:
            return self.overrides["tracks"][track_name]

        # First extract featured artists (this removes feat. parts)
        clean, _, _ = self.extract_featured_artists(track_name)
        
        # Remove common parentheticals for matching
        for pattern in self.TRACK_CLEAN_PATTERNS:
            clean = pattern.sub("", clean).strip()
            
        return self.normalize_case(clean)

    def get_fuzzy_score(self, a: str, b: str) -> float:
        """
        Calculate fuzzy matching score using Levenshtein + phonetic similarity.
        Returns score between 0.0 and 1.0.
        """
        if not a or not b:
            return 0.0

        # Normalize for comparison (unidecode handles diacritics)
        norm_a = unidecode(a).lower().strip()
        norm_b = unidecode(b).lower().strip()

        if norm_a == norm_b:
            return 1.0

        # Levenshtein ratio (0-100)
        levenshtein_score = fuzz.ratio(norm_a, norm_b) / 100.0

        # Phonetic similarity using Metaphone
        try:
            meta_a = metaphone(norm_a)
            meta_b = metaphone(norm_b)
            phonetic_score = 1.0 if meta_a and meta_b and meta_a == meta_b else 0.0
        except Exception:
            phonetic_score = 0.0

        # Handle "The" prefix specially for artists
        # "The National" vs "National" should score high
        if self._is_the_prefix_variant(norm_a, norm_b):
            return max(0.9, levenshtein_score)

        # Weighted combination (Levenshtein primary, phonetic secondary)
        return (levenshtein_score * 0.8) + (phonetic_score * 0.2)

    def _is_the_prefix_variant(self, a: str, b: str) -> bool:
        """Check if two strings differ only by 'the ' prefix."""
        if a.startswith("the ") and not b.startswith("the "):
            return a[4:] == b
        if b.startswith("the ") and not a.startswith("the "):
            return b[4:] == a
        return False

    def find_best_match(self, target: str, candidates: List[Tuple[str, int]], threshold: float = 0.85) -> Optional[NormalizationMatch]:
        """
        Find best fuzzy match for target string among candidates.
        Returns NormalizationMatch if found, None otherwise.
        """
        if not candidates:
            return None

        best_score = 0.0
        best_match = None

        # Use RapidFuzz for initial filtering
        candidate_names = [name for name, _ in candidates]
        matches = process.extract(target, candidate_names, scorer=fuzz.ratio, limit=5)

        for match_name, _, _ in matches:
            # Find the ID for this candidate
            candidate_id = next(cid for name, cid in candidates if name == match_name)
            
            # Calculate our enhanced fuzzy score
            score = self.get_fuzzy_score(target, match_name)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = NormalizationMatch(
                    canonical_id=candidate_id,
                    canonical_name=match_name,
                    confidence=score,
                    method="fuzzy_match",
                    notes=f"Levenshtein+Phonetic score: {score:.3f}"
                )

        return best_match

    def process_artists(self, dry_run: bool = False, fuzzy_threshold: float = 0.85) -> Dict[str, Any]:
        """Process artist normalization and canonicalization."""
        stats = {"processed": 0, "canonical_created": 0, "aliases_created": 0, "ambiguous_matches": 0}
        
        with connect(self.db_path) as db:
            # Get unique artists from both sources
            spotify_artists = db.execute("SELECT DISTINCT artist_name FROM raw_spotify_plays WHERE artist_name IS NOT NULL").fetchall()
            lastfm_artists = db.execute("SELECT DISTINCT artist_name FROM raw_lastfm_scrobbles WHERE artist_name IS NOT NULL").fetchall()
            
            all_raw_artists = {row["artist_name"] for row in spotify_artists} | {row["artist_name"] for row in lastfm_artists}
            
            # Get existing canonical artists for fuzzy matching
            existing_canonical = db.execute("SELECT id, name, normalized_name FROM canonical_artists").fetchall()
            canonical_pool = [(row["name"], row["id"]) for row in existing_canonical]
            canonical_by_slug = {row["normalized_name"]: row["id"] for row in existing_canonical}

            for raw_artist in sorted(all_raw_artists):
                stats["processed"] += 1
                
                # Normalize and split collaborations
                normalized_artists = self.normalize_artist_name_advanced(raw_artist)
                
                for norm_artist in normalized_artists:
                    slug = slugify_value(unidecode(norm_artist))
                    
                    # Check for exact slug match first
                    if slug in canonical_by_slug:
                        canonical_id = canonical_by_slug[slug]
                        self._create_artist_alias(db, raw_artist, slug, canonical_id, 1.0, "exact_match", dry_run)
                        stats["aliases_created"] += 1
                        continue

                    # Try fuzzy matching
                    match = self.find_best_match(norm_artist, canonical_pool, fuzzy_threshold)
                    
                    if match:
                        if match.confidence < 0.95:
                            # Log as ambiguous but still link
                            self.ambiguous_matches.append({
                                "type": "artist",
                                "raw": raw_artist,
                                "normalized": norm_artist,
                                "match": match.canonical_name,
                                "confidence": match.confidence,
                                "method": match.method
                            })
                            stats["ambiguous_matches"] += 1
                        
                        self._create_artist_alias(db, raw_artist, slug, match.canonical_id, match.confidence, match.method, dry_run)
                        stats["aliases_created"] += 1
                    else:
                        # Create new canonical artist
                        if not dry_run:
                            cur = db.execute(
                                "INSERT INTO canonical_artists (name, normalized_name) VALUES (?, ?)",
                                (norm_artist, slug)
                            )
                            canonical_id = cur.lastrowid
                            canonical_by_slug[slug] = canonical_id
                            canonical_pool.append((norm_artist, canonical_id))
                            stats["canonical_created"] += 1
                            self._create_artist_alias(db, raw_artist, slug, canonical_id, 1.0, "new_canonical", dry_run)
                            stats["aliases_created"] += 1
                        else:
                            stats["canonical_created"] += 1
                            stats["aliases_created"] += 1

        return stats

    def process_albums(self, dry_run: bool = False, fuzzy_threshold: float = 0.85) -> Dict[str, Any]:
        """Process album normalization and canonicalization."""
        stats = {"processed": 0, "canonical_created": 0, "aliases_created": 0, "ambiguous_matches": 0}
        
        with connect(self.db_path) as db:
            # Get unique album+artist combinations
            spotify_albums = db.execute(
                "SELECT DISTINCT artist_name, album_name FROM raw_spotify_plays WHERE album_name IS NOT NULL AND artist_name IS NOT NULL"
            ).fetchall()
            lastfm_albums = db.execute(
                "SELECT DISTINCT artist_name, album_name FROM raw_lastfm_scrobbles WHERE album_name IS NOT NULL AND artist_name IS NOT NULL"
            ).fetchall()
            
            all_combinations = {(row["artist_name"], row["album_name"]) for row in spotify_albums} | \
                             {(row["artist_name"], row["album_name"]) for row in lastfm_albums}

            for raw_artist, raw_album in sorted(all_combinations):
                stats["processed"] += 1
                
                # Get canonical artist ID
                artist_alias = db.execute(
                    "SELECT canonical_artist_id FROM artist_aliases WHERE raw_name = ? LIMIT 1", (raw_artist,)
                ).fetchone()
                artist_id = artist_alias["canonical_artist_id"] if artist_alias else None
                
                # Canonicalize album name
                canonical_album = self.canonicalize_album_name(raw_album)
                slug = slugify_value(unidecode(canonical_album))
                
                # Look for existing canonical album (scoped by artist)
                if artist_id:
                    existing = db.execute(
                        "SELECT id, title FROM canonical_albums WHERE normalized_title = ? AND (primary_artist_id = ? OR primary_artist_id IS NULL)",
                        (slug, artist_id)
                    ).fetchone()
                else:
                    existing = db.execute(
                        "SELECT id, title FROM canonical_albums WHERE normalized_title = ? AND primary_artist_id IS NULL",
                        (slug,)
                    ).fetchone()
                
                if existing:
                    self._create_album_alias(db, raw_album, slug, existing["id"], artist_id, 1.0, "exact_match", dry_run)
                    stats["aliases_created"] += 1
                    continue
                
                # Try fuzzy matching within artist's albums
                if artist_id:
                    artist_albums = db.execute(
                        "SELECT id, title FROM canonical_albums WHERE primary_artist_id = ?", (artist_id,)
                    ).fetchall()
                    candidates = [(row["title"], row["id"]) for row in artist_albums]
                    
                    match = self.find_best_match(canonical_album, candidates, fuzzy_threshold)
                    if match:
                        if match.confidence < 0.95:
                            self.ambiguous_matches.append({
                                "type": "album",
                                "raw": raw_album,
                                "artist": raw_artist,
                                "canonical": canonical_album,
                                "match": match.canonical_name,
                                "confidence": match.confidence,
                                "method": match.method
                            })
                            stats["ambiguous_matches"] += 1
                        
                        self._create_album_alias(db, raw_album, slug, match.canonical_id, artist_id, match.confidence, match.method, dry_run)
                        stats["aliases_created"] += 1
                        continue
                
                # Create new canonical album
                if not dry_run:
                    cur = db.execute(
                        "INSERT INTO canonical_albums (title, normalized_title, primary_artist_id) VALUES (?, ?, ?)",
                        (canonical_album, slug, artist_id)
                    )
                    album_id = cur.lastrowid
                    stats["canonical_created"] += 1
                    self._create_album_alias(db, raw_album, slug, album_id, artist_id, 1.0, "new_canonical", dry_run)
                    stats["aliases_created"] += 1
                else:
                    stats["canonical_created"] += 1
                    stats["aliases_created"] += 1
        
        return stats

    def process_tracks(self, dry_run: bool = False, fuzzy_threshold: float = 0.85) -> Dict[str, Any]:
        """Process track normalization and canonicalization."""
        stats = {"processed": 0, "canonical_created": 0, "aliases_created": 0, "ambiguous_matches": 0}
        
        with connect(self.db_path) as db:
            # Get unique track combinations
            spotify_tracks = db.execute(
                "SELECT DISTINCT artist_name, album_name, track_name FROM raw_spotify_plays WHERE track_name IS NOT NULL AND artist_name IS NOT NULL"
            ).fetchall()
            lastfm_tracks = db.execute(
                "SELECT DISTINCT artist_name, album_name, track_name FROM raw_lastfm_scrobbles WHERE track_name IS NOT NULL AND artist_name IS NOT NULL"
            ).fetchall()
            
            all_combinations = {(row["artist_name"], row["album_name"] or "", row["track_name"]) for row in spotify_tracks} | \
                             {(row["artist_name"], row["album_name"] or "", row["track_name"]) for row in lastfm_tracks}

            for raw_artist, raw_album, raw_track in sorted(all_combinations):
                stats["processed"] += 1
                
                # Get canonical artist and album IDs
                artist_alias = db.execute(
                    "SELECT canonical_artist_id FROM artist_aliases WHERE raw_name = ? LIMIT 1", (raw_artist,)
                ).fetchone()
                artist_id = artist_alias["canonical_artist_id"] if artist_alias else None
                
                album_id = None
                if raw_album:
                    album_alias = db.execute(
                        "SELECT canonical_album_id FROM album_aliases WHERE raw_title = ? AND (canonical_artist_id = ? OR canonical_artist_id IS NULL) LIMIT 1",
                        (raw_album, artist_id)
                    ).fetchone()
                    album_id = album_alias["canonical_album_id"] if album_alias else None
                
                # Canonicalize track name
                canonical_track = self.canonicalize_track_name(raw_track)
                slug = slugify_value(unidecode(canonical_track))
                
                # Look for existing canonical track
                if artist_id:
                    existing = db.execute(
                        "SELECT id, title FROM canonical_tracks WHERE normalized_title = ? AND primary_artist_id = ?",
                        (slug, artist_id)
                    ).fetchone()
                else:
                    existing = db.execute(
                        "SELECT id, title FROM canonical_tracks WHERE normalized_title = ? AND primary_artist_id IS NULL",
                        (slug,)
                    ).fetchone()
                
                if existing:
                    self._create_track_alias(db, raw_track, slug, existing["id"], artist_id, album_id, 1.0, "exact_match", dry_run)
                    stats["aliases_created"] += 1
                    continue
                
                # Try fuzzy matching within artist's tracks
                if artist_id:
                    artist_tracks = db.execute(
                        "SELECT id, title FROM canonical_tracks WHERE primary_artist_id = ?", (artist_id,)
                    ).fetchall()
                    candidates = [(row["title"], row["id"]) for row in artist_tracks]
                    
                    match = self.find_best_match(canonical_track, candidates, fuzzy_threshold)
                    if match:
                        if match.confidence < 0.95:
                            self.ambiguous_matches.append({
                                "type": "track",
                                "raw": raw_track,
                                "artist": raw_artist,
                                "canonical": canonical_track,
                                "match": match.canonical_name,
                                "confidence": match.confidence,
                                "method": match.method
                            })
                            stats["ambiguous_matches"] += 1
                        
                        self._create_track_alias(db, raw_track, slug, match.canonical_id, artist_id, album_id, match.confidence, match.method, dry_run)
                        stats["aliases_created"] += 1
                        continue
                
                # Create new canonical track
                if not dry_run:
                    cur = db.execute(
                        "INSERT INTO canonical_tracks (title, normalized_title, primary_artist_id, primary_album_id) VALUES (?, ?, ?, ?)",
                        (canonical_track, slug, artist_id, album_id)
                    )
                    track_id = cur.lastrowid
                    stats["canonical_created"] += 1
                    self._create_track_alias(db, raw_track, slug, track_id, artist_id, album_id, 1.0, "new_canonical", dry_run)
                    stats["aliases_created"] += 1
                else:
                    stats["canonical_created"] += 1
                    stats["aliases_created"] += 1
        
        return stats

    def process_all(self, dry_run: bool = False, fuzzy_threshold: float = 0.85) -> Dict[str, Any]:
        """Run the complete normalization pipeline."""
        self.ambiguous_matches = []
        
        artist_stats = self.process_artists(dry_run, fuzzy_threshold)
        album_stats = self.process_albums(dry_run, fuzzy_threshold)
        track_stats = self.process_tracks(dry_run, fuzzy_threshold)
        
        # Link raw plays to unified plays table
        if not dry_run:
            self.link_plays()
        
        return {
            "artists": artist_stats,
            "albums": album_stats,
            "tracks": track_stats,
            "total_ambiguous": len(self.ambiguous_matches)
        }

    def link_plays(self) -> Dict[str, int]:
        """Populate the plays table by linking raw plays to canonical entities."""
        stats = {"spotify_linked": 0, "lastfm_linked": 0, "skipped": 0}
        
        with connect(self.db_path) as db:
            # Link Spotify plays
            # NOTE: Use subquery with MIN(id) to pick exactly ONE track alias per (raw_title, artist)
            # to avoid creating duplicate plays when a track appears on multiple albums
            db.execute("""
                INSERT OR IGNORE INTO plays (
                    canonical_track_id, canonical_album_id, primary_artist_id,
                    play_timestamp_utc, duration_ms,
                    source_name, source_row_table, source_record_id,
                    location_country
                )
                SELECT 
                    ta.canonical_track_id,
                    ta.canonical_album_id,
                    ta.canonical_artist_id,
                    rsp.play_timestamp_utc,
                    rsp.ms_played,
                    'spotify',
                    'raw_spotify_plays',
                    rsp.id,
                    rsp.conn_country
                FROM raw_spotify_plays rsp
                JOIN track_aliases ta ON ta.id = (
                    SELECT MIN(ta2.id) FROM track_aliases ta2
                    WHERE ta2.raw_title = rsp.track_name 
                      AND ta2.canonical_artist_id = (
                          SELECT aa.canonical_artist_id 
                          FROM artist_aliases aa 
                          WHERE aa.raw_name = rsp.artist_name 
                          LIMIT 1
                      )
                )
                WHERE rsp.track_name IS NOT NULL AND rsp.artist_name IS NOT NULL
            """)
            stats["spotify_linked"] = db.execute("SELECT changes()").fetchone()[0]
            
            # Link Last.fm plays
            # NOTE: Same fix - pick exactly ONE track alias per (raw_title, artist)
            db.execute("""
                INSERT OR IGNORE INTO plays (
                    canonical_track_id, canonical_album_id, primary_artist_id,
                    play_timestamp_utc, source_name, source_row_table, source_record_id
                )
                SELECT 
                    ta.canonical_track_id,
                    ta.canonical_album_id,
                    ta.canonical_artist_id,
                    rls.utc_time,
                    'lastfm',
                    'raw_lastfm_scrobbles',
                    rls.id
                FROM raw_lastfm_scrobbles rls
                JOIN track_aliases ta ON ta.id = (
                    SELECT MIN(ta2.id) FROM track_aliases ta2
                    WHERE ta2.raw_title = rls.track_name 
                      AND ta2.canonical_artist_id = (
                          SELECT aa.canonical_artist_id 
                          FROM artist_aliases aa 
                          WHERE aa.raw_name = rls.artist_name 
                          LIMIT 1
                      )
                )
                WHERE rls.track_name IS NOT NULL AND rls.artist_name IS NOT NULL
            """)
            stats["lastfm_linked"] = db.execute("SELECT changes()").fetchone()[0]
            
            self._backfill_spotify_location(db)

        logger.info("Linked plays: Spotify=%d, Last.fm=%d", stats["spotify_linked"], stats["lastfm_linked"])
        return stats

    def _backfill_spotify_location(self, db: DatabaseSession) -> None:
        """Ensure existing Spotify plays carry over raw conn_country data."""
        db.execute(
            """
            UPDATE plays
            SET location_country = (
                SELECT conn_country
                FROM raw_spotify_plays rsp
                WHERE rsp.id = plays.source_record_id
            )
            WHERE source_name = 'spotify'
              AND source_row_table = 'raw_spotify_plays'
              AND location_country IS NULL
            """
        )

    def export_review(self, output_path: Path) -> None:
        """Export ambiguous matches for human review."""
        if not self.ambiguous_matches:
            logger.info("No ambiguous matches to export")
            return
            
        try:
            with output_path.open("w", encoding="utf-8") as fh:
                yaml.dump({
                    "ambiguous_matches": self.ambiguous_matches,
                    "instructions": "Review these matches and add corrections to normalization_overrides.yaml"
                }, fh, sort_keys=False, default_flow_style=False)
            logger.info("Exported %d ambiguous matches to %s", len(self.ambiguous_matches), output_path)
        except Exception as exc:
            logger.error("Failed to export review file: %s", exc)

    # Helper methods for database operations
    def _create_artist_alias(self, db: DatabaseSession, raw: str, slug: str, canonical_id: int, confidence: float, method: str, dry_run: bool) -> None:
        if dry_run:
            return
        db.execute(
            """
            INSERT OR IGNORE INTO artist_aliases 
            (raw_name, normalized_name, canonical_artist_id, match_confidence, match_method, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (raw, slug, canonical_id, confidence, method, "normalization")
        )

    def _create_album_alias(self, db: DatabaseSession, raw: str, slug: str, canonical_id: int, artist_id: Optional[int], confidence: float, method: str, dry_run: bool) -> None:
        if dry_run:
            return
        db.execute(
            """
            INSERT OR IGNORE INTO album_aliases 
            (raw_title, normalized_title, canonical_album_id, canonical_artist_id, match_confidence, match_method, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (raw, slug, canonical_id, artist_id, confidence, method, "normalization")
        )

    def _create_track_alias(self, db: DatabaseSession, raw: str, slug: str, canonical_id: int, artist_id: Optional[int], album_id: Optional[int], confidence: float, method: str, dry_run: bool) -> None:
        if dry_run:
            return
        db.execute(
            """
            INSERT OR IGNORE INTO track_aliases 
            (raw_title, normalized_title, canonical_track_id, canonical_artist_id, canonical_album_id, match_confidence, match_method, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (raw, slug, canonical_id, artist_id, album_id, confidence, method, "normalization")
        )
