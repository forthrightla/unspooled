-- 0001_initial.sql
-- Author: Josh / Playback Analytics
-- Description:
--   Foundational schema for the multi-source music playback warehouse.
--   Key design decisions:
--     * Raw tables mirror source exports for replayability.
--     * Canonical dimension tables are fully normalized and track provenance.
--     * Alias tables retain fuzzy matching attributes (confidence, method, reviewer).
--     * Plays fact table separates canonical relationships via junction tables to solve
--       "featuring artist" and "track on multiple albums" scenarios.
--     * Rich analytics support via timestamps, autoplay flags, device/platform metadata,
--       and geographic hints.

PRAGMA foreign_keys = ON;

BEGIN;

----------------------------------------------------------------------
-- Canonical dimensions
----------------------------------------------------------------------

CREATE TABLE canonical_artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    sort_name TEXT,
    musicbrainz_mbid TEXT UNIQUE,
    spotify_id TEXT UNIQUE,
    country TEXT,
    artist_type TEXT, -- Person, Group, Orchestra, Choir, Character, Other
    begin_date TEXT, -- formation/birth date
    end_date TEXT, -- dissolution/death date
    first_seen_play_at TEXT,
    last_seen_play_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_canonical_artists_mbz ON canonical_artists(musicbrainz_mbid);

CREATE TABLE canonical_albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    primary_artist_id INTEGER,
    release_date TEXT,
    release_year INTEGER,
    album_type TEXT, -- studio, live, compilation, single, etc.
    musicbrainz_mbid TEXT UNIQUE,
    spotify_id TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (primary_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL
);
CREATE INDEX idx_canonical_albums_primary_artist ON canonical_albums(primary_artist_id);
CREATE UNIQUE INDEX idx_canonical_albums_normalized ON canonical_albums(normalized_title, COALESCE(primary_artist_id, 0));

CREATE TABLE canonical_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    primary_artist_id INTEGER,
    primary_album_id INTEGER,
    duration_ms INTEGER,
    isrc TEXT UNIQUE,
    musicbrainz_recording_mbid TEXT UNIQUE,
    discovery_play_at TEXT, -- first time the listener encountered the track
    last_play_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (primary_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL,
    FOREIGN KEY (primary_album_id) REFERENCES canonical_albums(id) ON DELETE SET NULL
);
CREATE INDEX idx_canonical_tracks_primary_artist ON canonical_tracks(primary_artist_id);
CREATE UNIQUE INDEX idx_canonical_tracks_normalized ON canonical_tracks(normalized_title, COALESCE(primary_artist_id, 0));

-- Junction tables to handle multi-artist and multi-album relationships even after canonicalization.
CREATE TABLE canonical_track_artists (
    track_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    role TEXT DEFAULT 'primary', -- primary, featured, remixer, producer, etc.
    position INTEGER DEFAULT 1,
    PRIMARY KEY (track_id, artist_id, role),
    FOREIGN KEY (track_id) REFERENCES canonical_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY (artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE
);
CREATE INDEX idx_cta_artist_role ON canonical_track_artists(artist_id, role);

CREATE TABLE canonical_track_albums (
    track_id INTEGER NOT NULL,
    album_id INTEGER NOT NULL,
    disc_number INTEGER DEFAULT 1,
    track_number INTEGER,
    PRIMARY KEY (track_id, album_id, disc_number),
    FOREIGN KEY (track_id) REFERENCES canonical_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY (album_id) REFERENCES canonical_albums(id) ON DELETE CASCADE
);
CREATE INDEX idx_cta_album ON canonical_track_albums(album_id);

----------------------------------------------------------------------
-- Alias + fuzzy matching audit tables
----------------------------------------------------------------------

CREATE TABLE artist_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    canonical_artist_id INTEGER,
    match_confidence REAL NOT NULL DEFAULT 0.0, -- 0-1 score for auditing
    match_method TEXT NOT NULL, -- e.g., "exact", "levenshtein", "manual"
    source TEXT NOT NULL, -- spotify, lastfm, apple_music, manual
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (canonical_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL
);
CREATE INDEX idx_artist_aliases_norm ON artist_aliases(normalized_name);
CREATE INDEX idx_artist_aliases_canonical ON artist_aliases(canonical_artist_id);

CREATE TABLE album_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    canonical_album_id INTEGER,
    canonical_artist_id INTEGER,
    match_confidence REAL NOT NULL DEFAULT 0.0,
    match_method TEXT NOT NULL,
    source TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (canonical_album_id) REFERENCES canonical_albums(id) ON DELETE SET NULL,
    FOREIGN KEY (canonical_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL
);
CREATE INDEX idx_album_aliases_norm ON album_aliases(normalized_title);

CREATE TABLE track_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    canonical_track_id INTEGER,
    canonical_artist_id INTEGER,
    canonical_album_id INTEGER,
    match_confidence REAL NOT NULL DEFAULT 0.0,
    match_method TEXT NOT NULL,
    source TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (canonical_track_id) REFERENCES canonical_tracks(id) ON DELETE SET NULL,
    FOREIGN KEY (canonical_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL,
    FOREIGN KEY (canonical_album_id) REFERENCES canonical_albums(id) ON DELETE SET NULL
);
CREATE INDEX idx_track_aliases_norm ON track_aliases(normalized_title);

CREATE TABLE artist_genres (
    canonical_artist_id INTEGER NOT NULL,
    genre TEXT NOT NULL,
    source TEXT NOT NULL, -- spotify, musicbrainz, manual, etc.
    match_confidence REAL NOT NULL DEFAULT 1.0,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (canonical_artist_id, genre, source),
    FOREIGN KEY (canonical_artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE
);

----------------------------------------------------------------------
-- Raw source tables (append-only to preserve provenance)
----------------------------------------------------------------------

CREATE TABLE raw_spotify_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    source_row INTEGER,
    play_timestamp_utc TEXT,
    ms_played INTEGER,
    track_name TEXT,
    artist_name TEXT,
    album_name TEXT,
    spotify_track_uri TEXT,
    reason_start TEXT,
    reason_end TEXT,
    shuffle INTEGER,
    skipped INTEGER,
    offline INTEGER,
    offline_timestamp TEXT,
    incognito_mode INTEGER,
    platform TEXT,
    conn_country TEXT,
    ip_addr TEXT,
    metadata_flags TEXT,
    json_payload TEXT NOT NULL, -- entire row for replay/debugging
    raw_hash TEXT UNIQUE, -- SHA256 or similar to de-duplicate identical rows
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_spotify_timestamp ON raw_spotify_plays(play_timestamp_utc);
CREATE INDEX idx_raw_spotify_track_uri ON raw_spotify_plays(spotify_track_uri);

CREATE TABLE raw_lastfm_scrobbles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    source_row INTEGER,
    uts INTEGER,
    utc_time TEXT,
    artist_name TEXT,
    artist_mbid TEXT,
    album_name TEXT,
    album_mbid TEXT,
    track_name TEXT,
    track_mbid TEXT,
    duration_seconds INTEGER,
    application TEXT,
    album_missing INTEGER NOT NULL DEFAULT 0,
    duplicate_in_run INTEGER NOT NULL DEFAULT 0,
    json_payload TEXT,
    raw_hash TEXT UNIQUE,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_lastfm_time ON raw_lastfm_scrobbles(uts, utc_time);

CREATE TABLE raw_apple_music_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    track_name TEXT,
    artist_name TEXT,
    album_name TEXT,
    play_date_utc TEXT,
    duration_ms INTEGER,
    device TEXT,
    json_payload TEXT,
    raw_hash TEXT UNIQUE,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_apple_music_play_date ON raw_apple_music_plays(play_date_utc);

----------------------------------------------------------------------
-- Fact table + provenance
----------------------------------------------------------------------

CREATE TABLE plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_track_id INTEGER,
    canonical_album_id INTEGER,
    primary_artist_id INTEGER,
    play_timestamp_utc TEXT NOT NULL,
    play_timestamp_local TEXT,
    time_of_day_bucket TEXT, -- morning, afternoon, evening, late-night
    duration_ms INTEGER,
    ms_played INTEGER,
    user_initiated INTEGER NOT NULL DEFAULT 1, -- 1=user initiated, 0=autoplay/radio
    is_autoplay INTEGER NOT NULL DEFAULT 0,
    device_name TEXT,
    device_type TEXT,
    platform TEXT,
    context_source TEXT, -- playlist, album, radio, liked_songs, etc.
    location_country TEXT,
    location_region TEXT,
    location_city TEXT,
    latitude REAL,
    longitude REAL,
    source_name TEXT NOT NULL CHECK (source_name IN ('spotify','lastfm','apple_music','manual')),
    source_record_id INTEGER, -- references corresponding raw table row id
    source_row_table TEXT NOT NULL, -- raw table name, for auditing
    source_match_confidence REAL NOT NULL DEFAULT 1.0,
    ingestion_batch_id TEXT,
    -- Cross-source deduplication fields
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of_id INTEGER REFERENCES plays(id) ON DELETE SET NULL,
    dedupe_confidence INTEGER,
    dedupe_notes TEXT,
    dedupe_winner_source TEXT,
    deduped_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (canonical_track_id) REFERENCES canonical_tracks(id) ON DELETE SET NULL,
    FOREIGN KEY (canonical_album_id) REFERENCES canonical_albums(id) ON DELETE SET NULL,
    FOREIGN KEY (primary_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL
);
CREATE INDEX idx_plays_timestamp ON plays(play_timestamp_utc);
CREATE INDEX idx_plays_track ON plays(canonical_track_id);
CREATE INDEX idx_plays_artist ON plays(primary_artist_id);
CREATE INDEX idx_plays_source ON plays(source_name, source_record_id);
CREATE INDEX idx_plays_duplicate_flag ON plays(is_duplicate);
CREATE INDEX idx_plays_duplicate_of_id ON plays(duplicate_of_id);

-- Junction tables to capture featuring artists and album ambiguity per play.
CREATE TABLE plays_artists (
    play_id INTEGER NOT NULL,
    canonical_artist_id INTEGER NOT NULL,
    role TEXT DEFAULT 'primary',
    position INTEGER DEFAULT 1,
    PRIMARY KEY (play_id, canonical_artist_id, role),
    FOREIGN KEY (play_id) REFERENCES plays(id) ON DELETE CASCADE,
    FOREIGN KEY (canonical_artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE
);
CREATE INDEX idx_plays_artists_artist ON plays_artists(canonical_artist_id);

CREATE TABLE plays_albums (
    play_id INTEGER NOT NULL,
    canonical_album_id INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (play_id, canonical_album_id),
    FOREIGN KEY (play_id) REFERENCES plays(id) ON DELETE CASCADE,
    FOREIGN KEY (canonical_album_id) REFERENCES canonical_albums(id) ON DELETE CASCADE
);

-- Deduplication review queue for borderline matches requiring human review
CREATE TABLE dedupe_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    play_a_id INTEGER NOT NULL,
    play_b_id INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (play_a_id) REFERENCES plays(id) ON DELETE CASCADE,
    FOREIGN KEY (play_b_id) REFERENCES plays(id) ON DELETE CASCADE
);
CREATE INDEX idx_dedupe_review_confidence ON dedupe_review_queue(confidence);
CREATE INDEX idx_dedupe_review_resolved ON dedupe_review_queue(resolved);

----------------------------------------------------------------------
-- MusicBrainz cache
----------------------------------------------------------------------

CREATE TABLE musicbrainz_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL, -- artist, recording, release-group, etc.
    entity_id TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE (entity_type, entity_id, params_hash)
);
CREATE INDEX idx_musicbrainz_cache_expiry ON musicbrainz_cache(expires_at);

----------------------------------------------------------------------
-- Tags and genre mapping
----------------------------------------------------------------------

-- Raw tags from MusicBrainz (community-sourced)
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL,
    tag_count INTEGER DEFAULT 0, -- popularity/usage count from MB
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_tags_normalized ON tags(normalized_name);

-- Map MusicBrainz tags to canonical genres
CREATE TABLE genre_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mb_tag TEXT NOT NULL,
    canonical_genre TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0, -- 1 if this is the main genre, 0 if secondary/hierarchical
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (mb_tag, canonical_genre)
);
CREATE INDEX idx_genre_mapping_tag ON genre_mapping(mb_tag);
CREATE INDEX idx_genre_mapping_genre ON genre_mapping(canonical_genre);

-- Tags associated with artists
CREATE TABLE artist_tags (
    artist_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    score INTEGER DEFAULT 0, -- tag relevance score from MB (0-100)
    source TEXT DEFAULT 'musicbrainz',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (artist_id, tag_id),
    FOREIGN KEY (artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE INDEX idx_artist_tags_tag ON artist_tags(tag_id);

-- Tags associated with albums/releases
CREATE TABLE album_tags (
    album_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    source TEXT DEFAULT 'musicbrainz',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (album_id, tag_id),
    FOREIGN KEY (album_id) REFERENCES canonical_albums(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE INDEX idx_album_tags_tag ON album_tags(tag_id);

-- Enrichment tracking - what has been enriched and when
CREATE TABLE enrichment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL, -- artist, album, track
    entity_id INTEGER NOT NULL,
    enrichment_type TEXT NOT NULL, -- metadata, tags, album_lookup, etc.
    source TEXT NOT NULL DEFAULT 'musicbrainz',
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'success', -- success, partial, failed, skipped
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_enrichment_log_entity ON enrichment_log(entity_type, entity_id);
CREATE INDEX idx_enrichment_log_type ON enrichment_log(enrichment_type);

----------------------------------------------------------------------
-- Pre-computed analytics tables
----------------------------------------------------------------------

-- Artist-level computed analytics
CREATE TABLE artist_analytics (
    artist_id INTEGER PRIMARY KEY,
    first_play_date TEXT,
    last_play_date TEXT,
    total_plays INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    unique_tracks_played INTEGER NOT NULL DEFAULT 0,
    peak_period_start TEXT,
    peak_period_end TEXT,
    binge_score REAL, -- plays per day in first 30 days after discovery
    loyalty_tier TEXT, -- constant, phase, seasonal, one-and-done
    deep_cuts_ratio REAL, -- % of plays that are NOT in top 5 tracks
    days_since_last_play INTEGER,
    discovery_half_life INTEGER, -- days between first play and peak listening
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE
);

-- Album-level computed analytics
CREATE TABLE album_analytics (
    album_id INTEGER PRIMARY KEY,
    first_play_date TEXT,
    last_play_date TEXT,
    total_plays INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    unique_tracks_played INTEGER NOT NULL DEFAULT 0,
    completion_rate REAL, -- how often full album listened sequentially
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (album_id) REFERENCES canonical_albums(id) ON DELETE CASCADE
);

-- Track-level computed analytics
CREATE TABLE track_analytics (
    track_id INTEGER PRIMARY KEY,
    first_play_date TEXT,
    last_play_date TEXT,
    total_plays INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    morning_plays INTEGER NOT NULL DEFAULT 0, -- 6am-12pm
    afternoon_plays INTEGER NOT NULL DEFAULT 0, -- 12pm-6pm
    evening_plays INTEGER NOT NULL DEFAULT 0, -- 6pm-10pm
    night_plays INTEGER NOT NULL DEFAULT 0, -- 10pm-6am
    is_sleeper INTEGER NOT NULL DEFAULT 0, -- consistent plays over years but never binged
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (track_id) REFERENCES canonical_tracks(id) ON DELETE CASCADE
);

-- Monthly aggregates for temporal analysis
CREATE TABLE monthly_summary (
    year_month TEXT PRIMARY KEY, -- YYYY-MM format
    total_plays INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    unique_artists INTEGER NOT NULL DEFAULT 0,
    unique_albums INTEGER NOT NULL DEFAULT 0,
    unique_tracks INTEGER NOT NULL DEFAULT 0,
    new_artists_discovered INTEGER NOT NULL DEFAULT 0,
    top_artist_id INTEGER,
    top_artist_plays INTEGER,
    fragmentation_score REAL, -- unique artists / total plays
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (top_artist_id) REFERENCES canonical_artists(id) ON DELETE SET NULL
);

-- Hourly distribution (aggregate across all time)
CREATE TABLE hourly_distribution (
    hour INTEGER PRIMARY KEY CHECK (hour >= 0 AND hour < 24),
    total_plays INTEGER NOT NULL DEFAULT 0,
    avg_plays_per_day REAL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Day of week distribution
CREATE TABLE weekday_distribution (
    weekday INTEGER PRIMARY KEY CHECK (weekday >= 0 AND weekday < 7), -- 0=Sunday
    total_plays INTEGER NOT NULL DEFAULT 0,
    avg_plays_per_week REAL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Geographic analytics (when location data available)
CREATE TABLE geographic_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    region TEXT,
    city TEXT,
    total_plays INTEGER NOT NULL DEFAULT 0,
    first_play_date TEXT,
    last_play_date TEXT,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (country, region, city)
);
CREATE INDEX idx_geographic_country ON geographic_analytics(country);

-- Discovery/gateway artist relationships
CREATE TABLE discovery_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discovered_artist_id INTEGER NOT NULL,
    context_artist_id INTEGER NOT NULL,
    context_type TEXT NOT NULL, -- 'before', 'after', 'same_week'
    play_count INTEGER NOT NULL DEFAULT 1,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (discovered_artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE,
    FOREIGN KEY (context_artist_id) REFERENCES canonical_artists(id) ON DELETE CASCADE,
    UNIQUE (discovered_artist_id, context_artist_id, context_type)
);
CREATE INDEX idx_discovery_context_discovered ON discovery_context(discovered_artist_id);

-- Listening eras (clustered time periods with similar listening patterns)
CREATE TABLE listening_eras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    era_name TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    dominant_genre TEXT,
    top_artists TEXT, -- JSON array of artist IDs
    characteristic_tracks TEXT, -- JSON array of track IDs
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Analytics computation log for incremental updates
CREATE TABLE analytics_computation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    computation_type TEXT NOT NULL,
    entities_processed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running', -- running, completed, failed
    notes TEXT
);
CREATE INDEX idx_analytics_log_type ON analytics_computation_log(computation_type);

----------------------------------------------------------------------
-- Analytics helper views (optional but useful seed)
----------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS vw_play_counts_by_day AS
SELECT
    date(play_timestamp_utc) AS play_date,
    COUNT(*) AS play_count
FROM plays
GROUP BY date(play_timestamp_utc);

CREATE VIEW IF NOT EXISTS vw_artist_streak_hints AS
SELECT
    primary_artist_id,
    MIN(play_timestamp_utc) AS first_play,
    MAX(play_timestamp_utc) AS last_play,
    COUNT(*) AS total_plays
FROM plays
WHERE primary_artist_id IS NOT NULL
GROUP BY primary_artist_id;

COMMIT;
