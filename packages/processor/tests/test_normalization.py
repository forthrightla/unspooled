"""Unit tests for the NormalizationEngine."""

from __future__ import annotations

import pytest
from playback_analytics.config import Settings
from playback_analytics.normalization.engine import NormalizationEngine


@pytest.fixture
def engine(temp_settings: Settings) -> NormalizationEngine:
    """Create a NormalizationEngine instance for testing."""
    return NormalizationEngine(temp_settings)


def test_normalize_case(engine: NormalizationEngine):
    """Test case normalization."""
    assert engine.normalize_case("RADIOHEAD") == "Radiohead"
    assert engine.normalize_case("radiohead") == "radiohead"
    assert engine.normalize_case("Radiohead") == "Radiohead"
    assert engine.normalize_case("THE BEATLES") == "The Beatles"
    assert engine.normalize_case("") == ""
    assert engine.normalize_case("A") == "A"  # Single letter preserved


def test_split_collaborations(engine: NormalizationEngine):
    """Test collaboration splitting."""
    assert engine._split_collaborations("Artist A & Artist B") == ["Artist A", "Artist B"]
    assert engine._split_collaborations("Artist A and Artist B") == ["Artist A", "Artist B"]
    assert engine._split_collaborations("Artist A x Artist B") == ["Artist A", "Artist B"]
    assert engine._split_collaborations("Artist A vs Artist B") == ["Artist A", "Artist B"]
    assert engine._split_collaborations("Artist A vs. Artist B") == ["Artist A", "Artist B"]
    # Comma splitting removed intentionally - too aggressive (breaks "Earth, Wind & Fire")
    # Use manual overrides for comma-separated artist lists
    assert engine._split_collaborations("Artist A, Artist B") == ["Artist A, Artist B"]
    assert engine._split_collaborations("Solo Artist") == ["Solo Artist"]


def test_normalize_artist_name_advanced(engine: NormalizationEngine):
    """Test advanced artist name normalization."""
    # Basic case normalization
    assert engine.normalize_artist_name_advanced("RADIOHEAD") == ["Radiohead"]
    
    # Collaboration splitting
    assert set(engine.normalize_artist_name_advanced("Artist A & Artist B")) == {"Artist A", "Artist B"}
    
    # Empty/None handling
    assert engine.normalize_artist_name_advanced("") == []
    assert engine.normalize_artist_name_advanced(None) == []


def test_extract_featured_artists(engine: NormalizationEngine):
    """Test featured artist extraction from track names."""
    # Basic featuring patterns
    clean, featured, is_live = engine.extract_featured_artists("Song Name (feat. Artist B)")
    assert clean == "Song Name"
    assert featured == ["Artist B"]
    assert not is_live

    clean, featured, is_live = engine.extract_featured_artists("Song Name (featuring Artist B)")
    assert clean == "Song Name"
    assert featured == ["Artist B"]

    clean, featured, is_live = engine.extract_featured_artists("Song Name (with Artist B)")
    assert clean == "Song Name"
    assert featured == ["Artist B"]

    clean, featured, is_live = engine.extract_featured_artists("Song Name [ft. Artist B]")
    assert clean == "Song Name"
    assert featured == ["Artist B"]

    # Multiple featured artists
    clean, featured, is_live = engine.extract_featured_artists("Song (feat. Artist B & Artist C)")
    assert clean == "Song"
    assert set(featured) == {"Artist B", "Artist C"}

    # Live detection
    clean, featured, is_live = engine.extract_featured_artists("Song Name (Live at Venue)")
    assert is_live is True

    # No featuring
    clean, featured, is_live = engine.extract_featured_artists("Regular Song")
    assert clean == "Regular Song"
    assert featured == []
    assert not is_live


def test_canonicalize_album_name(engine: NormalizationEngine):
    """Test album name canonicalization."""
    assert engine.canonicalize_album_name("OK Computer (Deluxe Edition)") == "OK Computer"
    assert engine.canonicalize_album_name("The Bends [UK]") == "The Bends"
    assert engine.canonicalize_album_name("Kid A (Remastered)") == "Kid A"
    assert engine.canonicalize_album_name("Amnesiac (20th Anniversary Edition)") == "Amnesiac"
    assert engine.canonicalize_album_name("In Rainbows (Expanded Edition)") == "In Rainbows"
    assert engine.canonicalize_album_name("Hail to the Thief [Japan Bonus Tracks]") == "Hail to the Thief"
    assert engine.canonicalize_album_name("Regular Album") == "Regular Album"


def test_canonicalize_track_name(engine: NormalizationEngine):
    """Test track name canonicalization."""
    # Remove featuring and common parentheticals
    assert engine.canonicalize_track_name("Song (feat. Artist)") == "Song"
    assert engine.canonicalize_track_name("Song (Radio Edit)") == "Song"
    assert engine.canonicalize_track_name("Song (Album Version)") == "Song"
    # Remixes are intentionally kept as distinct works
    assert engine.canonicalize_track_name("Song (Remix)") == "Song (Remix)"
    assert engine.canonicalize_track_name("Song (Instrumental)") == "Song"
    
    # Preserve live versions (they should be different entities)
    live_clean = engine.canonicalize_track_name("Song (Live at Venue)")
    assert "Live" in live_clean or "live" in live_clean
    
    # Regular tracks
    assert engine.canonicalize_track_name("Regular Song") == "Regular Song"


def test_fuzzy_score_basic(engine: NormalizationEngine):
    """Test basic fuzzy matching scores."""
    # Identical strings
    assert engine.get_fuzzy_score("Radiohead", "Radiohead") == 1.0
    
    # Diacritics handling
    score = engine.get_fuzzy_score("Björk", "Bjork")
    assert score > 0.9  # Should be very high due to unidecode normalization
    
    # Case insensitive
    assert engine.get_fuzzy_score("RADIOHEAD", "radiohead") == 1.0
    
    # Empty strings
    assert engine.get_fuzzy_score("", "") == 0.0
    assert engine.get_fuzzy_score("test", "") == 0.0
    
    # Completely different
    score = engine.get_fuzzy_score("Radiohead", "Nirvana")
    assert score < 0.5


def test_the_prefix_handling(engine: NormalizationEngine):
    """Test 'The' prefix special handling."""
    # "The National" vs "National" should score very high
    score = engine.get_fuzzy_score("The National", "National")
    assert score >= 0.9
    
    score = engine.get_fuzzy_score("National", "The National")
    assert score >= 0.9
    
    # But not for unrelated words
    score = engine.get_fuzzy_score("The Beatles", "Rolling Stones")
    assert score < 0.5


def test_find_best_match(engine: NormalizationEngine):
    """Test fuzzy matching against candidate list."""
    candidates = [
        ("Radiohead", 1),
        ("The Beatles", 2),
        ("Pink Floyd", 3),
        ("Led Zeppelin", 4),
    ]
    
    # Exact match
    match = engine.find_best_match("Radiohead", candidates, 0.85)
    assert match is not None
    assert match.canonical_id == 1
    assert match.confidence == 1.0
    
    # Close match - "Radio Head" vs "Radiohead" should match but with lower threshold
    match = engine.find_best_match("Radio Head", candidates, 0.75)
    assert match is not None
    assert match.canonical_id == 1
    assert match.confidence > 0.75
    
    # No good match
    match = engine.find_best_match("Completely Different Artist", candidates, 0.85)
    assert match is None
    
    # Empty candidates
    match = engine.find_best_match("Any Artist", [], 0.85)
    assert match is None


def test_process_artists_dry_run(engine: NormalizationEngine):
    """Test artist processing in dry-run mode."""
    from playback_analytics.db.migrations import MigrationRunner
    from pathlib import Path
    
    # Apply migrations to create tables
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    runner = MigrationRunner(engine.db_path, migrations_dir)
    runner.apply_pending()
    
    stats = engine.process_artists(dry_run=True)
    
    assert "processed" in stats
    assert "canonical_created" in stats
    assert "aliases_created" in stats
    assert "ambiguous_matches" in stats
    
    # All counts should be non-negative
    assert stats["processed"] >= 0
    assert stats["canonical_created"] >= 0
    assert stats["aliases_created"] >= 0
    assert stats["ambiguous_matches"] >= 0


def test_process_albums_dry_run(engine: NormalizationEngine):
    """Test album processing in dry-run mode."""
    from playback_analytics.db.migrations import MigrationRunner
    from pathlib import Path
    
    # Apply migrations to create tables
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    runner = MigrationRunner(engine.db_path, migrations_dir)
    runner.apply_pending()
    
    stats = engine.process_albums(dry_run=True)
    
    assert "processed" in stats
    assert "canonical_created" in stats
    assert "aliases_created" in stats
    assert "ambiguous_matches" in stats


def test_process_tracks_dry_run(engine: NormalizationEngine):
    """Test track processing in dry-run mode."""
    from playback_analytics.db.migrations import MigrationRunner
    from pathlib import Path
    
    # Apply migrations to create tables
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    runner = MigrationRunner(engine.db_path, migrations_dir)
    runner.apply_pending()
    
    stats = engine.process_tracks(dry_run=True)
    
    assert "processed" in stats
    assert "canonical_created" in stats
    assert "aliases_created" in stats
    assert "ambiguous_matches" in stats


def test_process_all_dry_run(engine: NormalizationEngine):
    """Test full processing pipeline in dry-run mode."""
    from playback_analytics.db.migrations import MigrationRunner
    from pathlib import Path
    
    # Apply migrations to create tables
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    runner = MigrationRunner(engine.db_path, migrations_dir)
    runner.apply_pending()
    
    stats = engine.process_all(dry_run=True)
    
    assert "artists" in stats
    assert "albums" in stats
    assert "tracks" in stats
    assert "total_ambiguous" in stats
    
    # Each section should have the expected structure
    for section in ["artists", "albums", "tracks"]:
        section_stats = stats[section]
        assert "processed" in section_stats
        assert "canonical_created" in section_stats
        assert "aliases_created" in section_stats
        assert "ambiguous_matches" in section_stats


def test_load_overrides_missing_file(engine: NormalizationEngine):
    """Test behavior when override file doesn't exist."""
    # This should not raise an error
    engine._load_overrides()
    assert isinstance(engine.overrides, dict)


def test_export_review_empty(engine: NormalizationEngine, tmp_path):
    """Test exporting review when no ambiguous matches exist."""
    output_file = tmp_path / "test_review.yaml"
    
    # Should not create file when no ambiguous matches
    engine.ambiguous_matches = []
    engine.export_review(output_file)
    
    # File should not be created for empty matches
    assert not output_file.exists()


def test_export_review_with_matches(engine: NormalizationEngine, tmp_path):
    """Test exporting review with ambiguous matches."""
    output_file = tmp_path / "test_review.yaml"
    
    # Add some mock ambiguous matches
    engine.ambiguous_matches = [
        {
            "type": "artist",
            "raw": "Radio Head",
            "normalized": "Radio Head", 
            "match": "Radiohead",
            "confidence": 0.87,
            "method": "fuzzy_match"
        }
    ]
    
    engine.export_review(output_file)
    
    # File should be created
    assert output_file.exists()
    
    # File should contain YAML content
    content = output_file.read_text()
    assert "ambiguous_matches" in content
    assert "Radio Head" in content
    assert "Radiohead" in content
