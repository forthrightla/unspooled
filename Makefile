# Unspooled - Unified Makefile
# Commands to orchestrate the full pipeline: process → export → visualize

.PHONY: all process export dev build clean install help

# Default: run full pipeline
all: process export build

# Install dependencies for all packages
install:
	@echo "📦 Installing processor dependencies..."
	cd packages/processor && uv sync
	@echo "📦 Installing visualizer dependencies..."
	cd packages/visualizer && npm install
	@echo "✅ All dependencies installed"

# Run the processor pipeline (ingest, normalize, dedupe, enrich, analytics)
process:
	@echo "🔄 Running processor pipeline..."
	cd packages/processor && uv run python -m playback_analytics pipeline full \
		--config ../../config/settings.toml
	@echo "✅ Processing complete"

# Export database to JSON files for visualizer
export:
	@echo "📤 Exporting data to JSON..."
	cd packages/exporter && python export_data.py \
		../../data/processed/unspooled.sqlite \
		../../packages/visualizer/public/data
	@echo "✅ Export complete"

# Start development server
dev:
	@echo "🚀 Starting development server..."
	cd packages/visualizer && npm run dev

# Build static site
build:
	@echo "🏗️  Building static site..."
	cd packages/visualizer && npm run build
	@echo "✅ Build complete - output in packages/visualizer/out/"

# Clean generated files
clean:
	@echo "🧹 Cleaning generated files..."
	rm -rf data/processed/*.sqlite
	rm -rf data/exports/*
	rm -rf packages/visualizer/public/data/*.json
	rm -rf packages/visualizer/public/data/**/*.json
	rm -rf packages/visualizer/public/data/*.db
	rm -rf packages/visualizer/.next
	rm -rf packages/visualizer/out
	@echo "✅ Clean complete"

# Quick refresh: just export and rebuild (skip processing)
refresh: export build

# Database operations
db-init:
	cd packages/processor && uv run python -m playback_analytics db init \
		--config ../../config/settings.toml

db-stats:
	cd packages/processor && uv run python -m playback_analytics db stats \
		--config ../../config/settings.toml

db-backup:
	cd packages/processor && uv run python -m playback_analytics db backup \
		--config ../../config/settings.toml

# Individual processing steps
ingest-spotify:
	cd packages/processor && uv run python -m playback_analytics ingest spotify \
		--config ../../config/settings.toml

ingest-lastfm:
	cd packages/processor && uv run python -m playback_analytics ingest lastfm \
		--config ../../config/settings.toml

normalize:
	cd packages/processor && uv run python -m playback_analytics normalize all \
		--config ../../config/settings.toml

dedupe:
	cd packages/processor && uv run python -m playback_analytics dedupe run \
		--config ../../config/settings.toml

enrich:
	cd packages/processor && uv run python -m playback_analytics enrich all \
		--config ../../config/settings.toml

analytics:
	cd packages/processor && uv run python -m playback_analytics analytics compute \
		--config ../../config/settings.toml

# Run tests
test:
	cd packages/processor && uv run pytest -v

# Help
help:
	@echo "Unspooled - Personal Music Analytics"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Main targets:"
	@echo "  all          Run full pipeline (process → export → build)"
	@echo "  install      Install all dependencies"
	@echo "  process      Run processor pipeline"
	@echo "  export       Export database to JSON"
	@echo "  dev          Start development server"
	@echo "  build        Build static site"
	@echo "  clean        Remove generated files"
	@echo "  refresh      Quick rebuild (export + build, skip processing)"
	@echo ""
	@echo "Database:"
	@echo "  db-init      Initialize database"
	@echo "  db-stats     Show database statistics"
	@echo "  db-backup    Create database backup"
	@echo ""
	@echo "Individual steps:"
	@echo "  ingest-spotify   Ingest Spotify data"
	@echo "  ingest-lastfm    Ingest Last.fm data"
	@echo "  normalize        Run normalization"
	@echo "  dedupe           Run deduplication"
	@echo "  enrich           Run MusicBrainz enrichment"
	@echo "  analytics        Compute analytics"
	@echo ""
	@echo "Testing:"
	@echo "  test         Run processor tests"
