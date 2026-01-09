# Unspooled Exporter

Transforms the SQLite database from the processor into optimized JSON files for the visualizer.

**Part of the [Unspooled](../../README.md) project.**

## Quickstart

This package is typically used via the root Makefile:

```bash
# From repo root
make export
```

For standalone use:

```bash
python export_data.py <database_path> <output_dir>

# Example:
python export_data.py ../../data/processed/unspooled.sqlite ../../packages/visualizer/public/data
```

## Output Files

The exporter generates the following JSON files:

| File | Description |
|------|-------------|
| `overview.json` | Homepage stats (total plays, top artist, etc.) |
| `timeline.json` | Monthly play counts with top artists |
| `temporal.json` | Hourly and weekday distribution |
| `genres.json` | Genre breakdown with play counts |
| `geography.json` | Geographic listening data |
| `artist-monthly.json` | Monthly plays per artist |
| `discoveries-detailed.json` | Artist discovery timeline |
| `artists.json` | Search index for artists |
| `albums.json` | Search index for albums |
| `artists/index.json` | All artists with stats |
| `artists/{id}.json` | Individual artist details |
| `albums/index.json` | All albums with stats |
| `tracks/index.json` | All tracks with stats |
| `story/{year}.json` | Year-in-review data |
| `listening.db` | Slim database for advanced queries |

## Dependencies

The exporter uses only Python standard library (sqlite3, json, pathlib).
No additional packages required.
