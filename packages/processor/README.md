# Unspooled Processor

Python pipeline that ingests multiple music data sources (Spotify, Last.fm, Apple Music), normalizes and deduplicates them, enriches metadata via MusicBrainz, and publishes a clean SQLite database for downstream analysis.

**Part of the [Unspooled](../../README.md) project.**

## Quickstart

This package is typically used via the root Makefile:

```bash
# From repo root
make process
```

For standalone use:

```bash
# Install dependencies
uv sync

# Run full pipeline
uv run python -m playback_analytics pipeline full --config ../../config/settings.toml
```

## Package Layout

```
├── migrations/                     # Ordered SQL migrations (0001_*.sql)
├── src/
│   └── playback_analytics/
│       ├── config/                 # Config models + loader
│       ├── ingestion/              # Connectors for Spotify, Last.fm, Apple Music
│       ├── normalization/          # Field normalization / unit conversions
│       ├── deduplication/          # Fuzzy matching + canonicalization
│       ├── enrichment/             # MusicBrainz lookups + caching
│       ├── analytics/              # Pre-computed analytics engine
│       └── db/                     # SQLite access + migrations
├── tests/                          # Test suite
└── pyproject.toml                  # Package definition
```

## CLI Commands

```bash
# Full pipeline
python -m playback_analytics pipeline full --config <path>

# Individual steps
python -m playback_analytics ingest spotify --config <path>
python -m playback_analytics ingest lastfm --config <path>
python -m playback_analytics normalize all --config <path>
python -m playback_analytics dedupe run --config <path>
python -m playback_analytics enrich all --config <path>
python -m playback_analytics analytics compute --config <path>

# Database management
python -m playback_analytics db init --config <path>
python -m playback_analytics db stats --config <path>
python -m playback_analytics db backup --config <path>
```

## Architecture

- **Raw data preservation:** raw tables mirror upstream payloads so dedupe bugs can be replayed
- **Canonical layer:** `canonical_*` tables represent deduplicated entities linked by alias tables with match confidence
- **Rich plays fact table:** captures timestamps, device/platform, autoplay flag, geographic hints, and provenance
- **Association tables:** `plays_artists`, `plays_albums`, and `canonical_track_albums` manage featuring artists and multi-album appearances
- **Migration support:** SQL files in `migrations/` are applied in lexical order

See `migrations/0001_initial.sql` for the full schema and design commentary.
