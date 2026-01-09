# Unspooled

Personal music listening analytics: ingest your Spotify, Last.fm, and Apple Music history → process and enrich → visualize with beautiful Wrapped-style dashboards.

## Overview

Unspooled is a three-part system:

1. **Processor** (`packages/processor/`) - Python pipeline that ingests raw exports, normalizes artists/albums/tracks, deduplicates cross-source plays, enriches via MusicBrainz, and computes analytics
2. **Exporter** (`packages/exporter/`) - Transforms the SQLite database into optimized JSON files for the web
3. **Visualizer** (`packages/visualizer/`) - Next.js static site with Wrapped-style visualizations of your complete listening history

## Quickstart

### 1. Setup

```bash
# Clone the repo
git clone https://github.com/josh/unspooled.git
cd unspooled

# Copy config template
cp config/settings.example.toml config/settings.toml

# Install dependencies
make install
```

### 2. Add Your Data

Place your music export files in `data/input/`:

- **Spotify**: Request your [Extended Streaming History](https://www.spotify.com/account/privacy/) and copy the `Streaming_History_Audio_*.json` files
- **Last.fm**: Export from [Last.fm Tools](https://lastfm.ghan.nl/export/) or similar
- **Apple Music**: Export your library XML (optional)

### 3. Run the Pipeline

```bash
# Full pipeline: process → export → build
make all

# Or step by step:
make process   # Ingest, normalize, dedupe, enrich, compute analytics
make export    # Generate JSON files
make build     # Build static site
```

### 4. View Your Data

```bash
# Start dev server
make dev

# Open http://localhost:3000
```

## Project Structure

```
unspooled/
├── packages/
│   ├── processor/          # Python analytics pipeline
│   │   ├── src/playback_analytics/
│   │   ├── tests/
│   │   └── migrations/
│   ├── exporter/           # Database → JSON export
│   └── visualizer/         # Next.js dashboard
├── config/
│   └── settings.toml       # Your configuration
├── data/
│   ├── input/              # Raw exports (Spotify, Last.fm, etc.)
│   ├── processed/          # SQLite databases
│   └── exports/            # Intermediate files
├── Makefile                # Orchestration commands
└── README.md
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make all` | Run full pipeline (process → export → build) |
| `make install` | Install all dependencies |
| `make process` | Run processor pipeline |
| `make export` | Export database to JSON |
| `make dev` | Start development server |
| `make build` | Build static site |
| `make clean` | Remove generated files |
| `make refresh` | Quick rebuild (export + build only) |
| `make test` | Run processor tests |

## Configuration

Edit `config/settings.toml` to customize paths and behavior:

```toml
[paths]
input_dir = "../../data/input"
database_path = "../../data/processed/unspooled.sqlite"
export_output = "../../packages/visualizer/public/data"

[ingestion.spotify]
min_duration_seconds = 30  # Skip short plays
skip_podcasts = true

[enrichment]
enabled = true  # Fetch metadata from MusicBrainz
```

## Features

### Processor
- Multi-source ingestion (Spotify Extended History, Last.fm scrobbles, Apple Music)
- Fuzzy matching and deduplication across sources
- MusicBrainz metadata enrichment (genres, countries, release dates)
- Pre-computed analytics (play counts, listening patterns, discovery tracking)

### Visualizer
- Overview dashboard with lifetime stats
- Artist/album/track deep dives with timeline charts
- Year-in-review "Story" mode (Wrapped-style slides)
- Discovery tracking (when you found new artists)
- Temporal patterns (peak hours, weekend vs weekday)
- Full-text search across your library

## Requirements

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) (Python package manager)

## License

MIT
