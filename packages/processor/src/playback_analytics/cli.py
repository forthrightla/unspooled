"""Typer CLI entrypoint for the playback analytics pipeline."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import typer
import yaml

from playback_analytics import get_version
from playback_analytics.analytics import AnalyticsEngine
from playback_analytics.config import load_settings
from playback_analytics.console import (
    console,
    confirm_action,
    create_progress,
    format_number,
    print_error,
    print_header,
    print_info,
    print_pipeline_summary,
    print_step,
    print_success,
    print_summary_table,
    print_warning,
)
from playback_analytics.db import MigrationRunner, connect
from playback_analytics.deduplication import DeduplicationEngine
from playback_analytics.enrichment import MusicBrainzEnricher
from playback_analytics.ingestion import LastFMIngestor, SpotifyIngestor
from playback_analytics.logging import configure_logging
from playback_analytics.normalization.engine import NormalizationEngine
from playback_analytics.pipelines import PlaybackPipeline

app = typer.Typer(help="Personal music listening analytics toolkit.")
ingest_app = typer.Typer(help="Data ingestion from various sources.")
normalize_app = typer.Typer(help="Normalization and canonicalization commands.")
dedupe_app = typer.Typer(help="Cross-source deduplication commands.")
enrich_app = typer.Typer(help="MusicBrainz metadata enrichment commands.")
analytics_app = typer.Typer(help="Pre-computed analytics and insights.")
pipeline_app = typer.Typer(help="Pipeline orchestration commands.")
db_app = typer.Typer(help="Database management commands.")
config_app = typer.Typer(help="Configuration management.")
review_app = typer.Typer(help="Human review workflow.")

app.add_typer(ingest_app, name="ingest")
app.add_typer(normalize_app, name="normalize")
app.add_typer(dedupe_app, name="dedupe")
app.add_typer(enrich_app, name="enrich")
app.add_typer(analytics_app, name="analytics")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(db_app, name="db")
app.add_typer(config_app, name="config")
app.add_typer(review_app, name="review")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@app.command()
def version() -> None:
    """Display the package version."""
    typer.echo(f"playback-analytics {get_version()}")


@app.command()
def migrate(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    migrations_dir: Path = typer.Option(
        Path(__file__).resolve().parents[2] / "migrations",
        exists=True,
        help="Directory containing ordered SQL migrations.",
    ),
    dry_run: bool = typer.Option(False, help="Show pending migrations without applying."),
) -> None:
    """Apply pending database migrations."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    runner = MigrationRunner(settings.paths.database_path, migrations_dir)
    if dry_run:
        pending = runner.pending_migrations(dry_run=True)
        if pending:
            typer.echo(
                json.dumps({"status": "pending", "migrations": pending}, indent=2)
            )
        else:
            typer.echo(json.dumps({"status": "ok", "migrations": []}, indent=2))
        return
    applied = runner.apply_pending()
    if applied:
        typer.echo(f"Applied migrations: {', '.join(applied)}")
    else:
        typer.echo("No migrations needed.")


@app.command()
def ingest_spotify(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    apply_migrations: bool = typer.Option(True, help="Run migrations before ingestion."),
    progress: bool = typer.Option(True, help="Show progress spinner."),
    dry_run: bool = typer.Option(False, help="Parse files without writing to the database."),
) -> None:
    """Ingest Spotify Extended Streaming History exports."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    if apply_migrations and not dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        runner.apply_pending()
    elif apply_migrations and dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        pending = runner.pending_migrations(dry_run=True)
        if pending:
            typer.echo(
                json.dumps({"note": "dry-run", "pending_migrations": pending}, indent=2)
            )
    ingestor = SpotifyIngestor(settings)
    stats = ingestor.ingest(show_progress=progress, dry_run=dry_run)
    typer.echo(json.dumps(stats.to_summary(), indent=2))


@app.command()
def ingest_lastfm(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    apply_migrations: bool = typer.Option(True, help="Run migrations before ingestion."),
    progress: bool = typer.Option(True, help="Show progress spinner."),
    dry_run: bool = typer.Option(False, help="Parse files without writing to the database."),
) -> None:
    """Ingest Last.fm CSV exports."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    if apply_migrations and not dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        runner.apply_pending()
    elif apply_migrations and dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        pending = runner.pending_migrations(dry_run=True)
        if pending:
            typer.echo(
                json.dumps({"note": "dry-run", "pending_migrations": pending}, indent=2)
            )
    ingestor = LastFMIngestor(settings)
    stats = ingestor.ingest(show_progress=progress, dry_run=dry_run)
    typer.echo(json.dumps(stats.to_summary(), indent=2))


@app.command()
def run(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    skip_migrations: bool = typer.Option(
        False, help="Skip automatic migration enforcement before pipeline run."
    ),
    dry_run: bool = typer.Option(False, help="Report what would run without modifying the database."),
) -> None:
    """Execute the ingestion + normalization pipeline (persistence TBD)."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    if not skip_migrations and not dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        runner.apply_pending()
    elif not skip_migrations and dry_run:
        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        runner = MigrationRunner(settings.paths.database_path, migrations_dir)
        pending = runner.pending_migrations(dry_run=True)
        typer.echo(json.dumps({"note": "dry-run", "pending_migrations": pending}, indent=2))
        typer.echo("Dry-run: pipeline execution not triggered.")
        return
    pipeline = PlaybackPipeline(settings)
    stats = pipeline.run()
    typer.echo(f"Pipeline completed with {stats.normalized_events} normalized events.")


@normalize_app.command("artists")
def normalize_artists(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dry_run: bool = typer.Option(False, help="Perform normalization without writing to the database."),
    fuzzy_threshold: float = typer.Option(0.85, help="Fuzzy matching threshold (0.0-1.0)."),
) -> None:
    """Normalize and canonicalize artists."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = NormalizationEngine(settings)

    with create_progress() as progress:
        task = progress.add_task("Normalizing artists...", total=None)
        stats = engine.process_artists(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task, completed=True)

    print_summary_table("Artist Normalization", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@normalize_app.command("albums")
def normalize_albums(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dry_run: bool = typer.Option(False, help="Perform normalization without writing to the database."),
    fuzzy_threshold: float = typer.Option(0.85, help="Fuzzy matching threshold (0.0-1.0)."),
) -> None:
    """Normalize and canonicalize albums."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = NormalizationEngine(settings)

    with create_progress() as progress:
        task = progress.add_task("Normalizing albums...", total=None)
        stats = engine.process_albums(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task, completed=True)

    print_summary_table("Album Normalization", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@normalize_app.command("tracks")
def normalize_tracks(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dry_run: bool = typer.Option(False, help="Perform normalization without writing to the database."),
    fuzzy_threshold: float = typer.Option(0.85, help="Fuzzy matching threshold (0.0-1.0)."),
) -> None:
    """Normalize and canonicalize tracks."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = NormalizationEngine(settings)

    with create_progress() as progress:
        task = progress.add_task("Normalizing tracks...", total=None)
        stats = engine.process_tracks(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task, completed=True)

    print_summary_table("Track Normalization", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@normalize_app.command("all")
def normalize_all(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dry_run: bool = typer.Option(False, help="Perform normalization without writing to the database."),
    fuzzy_threshold: float = typer.Option(0.85, help="Fuzzy matching threshold (0.0-1.0)."),
) -> None:
    """Run full normalization pipeline (artists, then albums, then tracks)."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = NormalizationEngine(settings)

    print_header("Normalization Pipeline", "Processing artists, albums, and tracks")

    with create_progress() as progress:
        task1 = progress.add_task("[1/4] Normalizing artists...", total=None)
        artist_stats = engine.process_artists(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task1, completed=True)

        task2 = progress.add_task("[2/4] Normalizing albums...", total=None)
        album_stats = engine.process_albums(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task2, completed=True)

        task3 = progress.add_task("[3/4] Normalizing tracks...", total=None)
        track_stats = engine.process_tracks(dry_run=dry_run, fuzzy_threshold=fuzzy_threshold)
        progress.update(task3, completed=True)

        task4 = progress.add_task("[4/4] Linking plays...", total=None)
        if not dry_run:
            engine.link_plays()
        progress.update(task4, completed=True)

    print_summary_table("Artist Normalization", artist_stats)
    print_summary_table("Album Normalization", album_stats)
    print_summary_table("Track Normalization", track_stats)

    if dry_run:
        print_warning("Dry run - no data written")


@normalize_app.command("review")
def normalize_review(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    output: Path = typer.Option("ambiguous_matches.yaml", help="Path to export the review file."),
    fuzzy_threshold: float = typer.Option(0.85, help="Fuzzy matching threshold (0.0-1.0)."),
) -> None:
    """Export ambiguous matches for human review."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = NormalizationEngine(settings)
    # Run normalization in dry-run mode to collect ambiguous matches
    engine.process_all(dry_run=True, fuzzy_threshold=fuzzy_threshold)
    engine.export_review(output)
    typer.echo(f"Review file exported to: {output}")


@dedupe_app.command("run")
def dedupe_run(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    window_seconds: int = typer.Option(60, help="Timestamp matching window in seconds."),
    fuzzy_threshold: float = typer.Option(0.9, help="Fuzzy title match threshold (0.0-1.0)."),
    duration_tolerance: float = typer.Option(0.10, help="Allowed duration variance (fraction)."),
    dry_run: bool = typer.Option(False, help="Compute matches without updating the database."),
) -> None:
    """Run the deduplication engine across all plays."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = DeduplicationEngine(settings)

    print_header("Deduplication", "Finding cross-source duplicates")

    with create_progress() as progress:
        task = progress.add_task("Scanning for duplicates...", total=None)
        stats = engine.run(
            window_seconds=window_seconds,
            fuzzy_threshold=fuzzy_threshold,
            duration_tolerance=duration_tolerance,
            dry_run=dry_run,
        )
        progress.update(task, completed=True)

    print_summary_table("Deduplication Results", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@dedupe_app.command("report")
def dedupe_report(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Display deduplication summary metrics."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = DeduplicationEngine(settings)
    typer.echo(json.dumps(engine.report(), indent=2))


@dedupe_app.command("review")
def dedupe_review(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    output: Path = typer.Option("dedupe_review.yaml", help="Where to write pending review pairs."),
) -> None:
    """Export borderline duplicate pairs for manual resolution."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = DeduplicationEngine(settings)
    engine.export_review(output)
    typer.echo(f"Review entries exported to: {output}")


@dedupe_app.command("undo")
def dedupe_undo(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Reset deduplication flags to rerun with different parameters."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = DeduplicationEngine(settings)

    with create_progress() as progress:
        task = progress.add_task("Resetting deduplication flags...", total=None)
        stats = engine.undo()
        progress.update(task, completed=True)

    print_summary_table("Deduplication Undo", stats)


@enrich_app.command("artists")
def enrich_artists(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    limit: int = typer.Option(100, help="Maximum number of artists to process."),
    dry_run: bool = typer.Option(False, help="Preview enrichment without writing to database."),
) -> None:
    """Enrich artists with MusicBrainz metadata (country, type, tags)."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    print_header("Artist Enrichment", f"Processing up to {limit} artists via MusicBrainz")

    progress = create_enrichment_progress()
    task_id = None

    def update_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "Enriching artists...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        stats = enricher.enrich_artists(dry_run=dry_run, limit=limit, progress_callback=update_progress)

    print_summary_table("Artist Enrichment Results", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@enrich_app.command("albums")
def enrich_albums(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    limit: int = typer.Option(100, help="Maximum number of albums to process."),
    dry_run: bool = typer.Option(False, help="Preview enrichment without writing to database."),
) -> None:
    """Enrich albums with MusicBrainz metadata (release date, tags)."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    print_header("Album Enrichment", f"Processing up to {limit} albums via MusicBrainz")

    progress = create_enrichment_progress()
    task_id = None

    def update_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "Enriching albums...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        stats = enricher.enrich_albums(dry_run=dry_run, limit=limit, progress_callback=update_progress)

    print_summary_table("Album Enrichment Results", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@enrich_app.command("missing-albums")
def enrich_missing_albums(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    limit: int = typer.Option(100, help="Maximum number of tracks to process."),
    dry_run: bool = typer.Option(False, help="Preview enrichment without writing to database."),
) -> None:
    """Find and link missing album data for tracks via MusicBrainz."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    print_header("Missing Album Lookup", f"Processing up to {limit} tracks via MusicBrainz")

    progress = create_enrichment_progress()
    task_id = None

    def update_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "Finding albums...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        stats = enricher.find_missing_albums(dry_run=dry_run, limit=limit, progress_callback=update_progress)

    print_summary_table("Missing Album Results", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@enrich_app.command("genres")
def enrich_genres(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    limit: int = typer.Option(100, help="Maximum number of artists to process."),
    dry_run: bool = typer.Option(False, help="Preview enrichment without writing to database."),
) -> None:
    """Fetch genre/tag data for artists from MusicBrainz."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    print_header("Genre Enrichment", f"Processing up to {limit} artists via MusicBrainz")

    progress = create_enrichment_progress()
    task_id = None

    def update_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "Fetching genres...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        stats = enricher.enrich_genres(dry_run=dry_run, limit=limit, progress_callback=update_progress)

    print_summary_table("Genre Enrichment Results", stats)
    if dry_run:
        print_warning("Dry run - no data written")


@enrich_app.command("all")
def enrich_all(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    limit: Optional[int] = typer.Option(None, help="Maximum entities per category (default: no limit)."),
    dry_run: bool = typer.Option(False, help="Preview enrichment without writing to database."),
) -> None:
    """Run full MusicBrainz enrichment pipeline."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    limit_desc = f"up to {limit}" if limit else "all"
    print_header("Full Enrichment Pipeline", f"Processing {limit_desc} entities per category")

    all_results = {}

    # Artists
    progress = create_enrichment_progress()
    task_id = None

    def update_artist_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[1/4] Enriching artists...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        all_results["artists"] = enricher.enrich_artists(dry_run=dry_run, limit=limit, progress_callback=update_artist_progress)

    # Missing albums (run first to add MBIDs before album enrichment)
    progress = create_enrichment_progress()
    task_id = None

    def update_missing_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[2/4] Finding missing albums...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        all_results["missing_albums"] = enricher.find_missing_albums(dry_run=dry_run, limit=limit, progress_callback=update_missing_progress)

    # Albums (now can use MBIDs from missing albums step)
    progress = create_enrichment_progress()
    task_id = None

    def update_album_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[3/4] Enriching albums...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        all_results["albums"] = enricher.enrich_albums(dry_run=dry_run, limit=limit, progress_callback=update_album_progress)

    # Genres
    progress = create_enrichment_progress()
    task_id = None

    def update_genre_progress(stats):
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[4/4] Fetching genres...",
                total=stats.total_items,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )
        progress.update(
            task_id,
            completed=stats.current_item,
            current=stats.current_entity_name,
            eta=format_time_remaining(stats.estimated_seconds_remaining),
        )

    with progress:
        all_results["genres"] = enricher.enrich_genres(dry_run=dry_run, limit=limit, progress_callback=update_genre_progress)

    print_summary_table("Artist Enrichment", all_results["artists"])
    print_summary_table("Missing Albums", all_results["missing_albums"])
    print_summary_table("Album Enrichment", all_results["albums"])
    print_summary_table("Genre Enrichment", all_results["genres"])

    if dry_run:
        print_warning("Dry run - no data written")


@enrich_app.command("status")
def enrich_status(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Show enrichment coverage statistics."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    enricher = MusicBrainzEnricher(settings)

    with create_progress() as progress:
        task = progress.add_task("Loading enrichment status...", total=None)
        stats = enricher.status()
        progress.update(task, completed=True)

    print_header("Enrichment Coverage")
    print_summary_table("Artists", stats.get("artists", {}))
    print_summary_table("Albums", stats.get("albums", {}))
    print_summary_table("Tracks", stats.get("tracks", {}))
    print_summary_table("Tags & Cache", {"total_tags": stats.get("tags", {}).get("total", 0), "cache_entries": stats.get("cache", {}).get("entries", 0)})


@enrich_app.command("download-db")
def enrich_download_db(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dump_type: str = typer.Option(
        "all",
        help="Which dump to download: all, artist, release-group, recording",
    ),
) -> None:
    """Download MusicBrainz JSON dumps for local enrichment."""
    from playback_analytics.enrichment.local_mb import download_dump, MB_DUMPS

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    
    dump_dir = settings.paths.database_path.parent / "musicbrainz_dumps"
    
    print_header("MusicBrainz Dump Download", f"Downloading to {dump_dir}")
    
    if dump_type == "all":
        for dt in MB_DUMPS.keys():
            try:
                download_dump(dt, dump_dir)
            except Exception as e:
                print_error(f"Failed to download {dt}: {e}")
    else:
        try:
            download_dump(dump_type, dump_dir)
        except Exception as e:
            print_error(f"Failed to download {dump_type}: {e}")
    
    print_success("Download complete")


@enrich_app.command("import-db")
def enrich_import_db(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    dump_type: str = typer.Option(
        "all",
        help="Which dump to import: all, artist, release-group, recording",
    ),
) -> None:
    """Import MusicBrainz JSON dumps into local SQLite database."""
    from playback_analytics.enrichment.local_mb import LocalMusicBrainzDB, MB_DUMPS

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    
    dump_dir = settings.paths.database_path.parent / "musicbrainz_dumps"
    local_db_path = settings.paths.database_path.parent / "musicbrainz_local.sqlite"
    
    print_header("MusicBrainz Import", f"Importing to {local_db_path}")
    
    local_db = LocalMusicBrainzDB(local_db_path)
    
    import_map = {
        "artist": ("artist.tar.xz", local_db.import_artists),
        "release-group": ("release-group.tar.xz", local_db.import_release_groups),
        "recording": ("recording.tar.xz", local_db.import_recordings),
    }
    
    types_to_import = list(import_map.keys()) if dump_type == "all" else [dump_type]
    
    for dt in types_to_import:
        if dt not in import_map:
            print_error(f"Unknown dump type: {dt}")
            continue
        
        filename, import_fn = import_map[dt]
        dump_path = dump_dir / filename
        
        if not dump_path.exists():
            print_warning(f"Dump file not found: {dump_path}")
            print_info(f"Run: playback-analytics enrich download-db --config {config} --dump-type {dt}")
            continue
        
        try:
            import_fn(dump_path)
        except Exception as e:
            print_error(f"Failed to import {dt}: {e}")
    
    # Show status
    status = local_db.get_import_status()
    print_summary_table("Import Status", {k: v.get("record_count", 0) for k, v in status.items()})
    print_success("Import complete")


@enrich_app.command("local-status")
def enrich_local_status(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Show status of local MusicBrainz database."""
    from playback_analytics.enrichment.local_mb import LocalMusicBrainzDB

    settings = load_settings(config)
    local_db_path = settings.paths.database_path.parent / "musicbrainz_local.sqlite"
    
    if not local_db_path.exists():
        print_warning("Local MusicBrainz database not found")
        print_info("Run: playback-analytics enrich download-db && playback-analytics enrich import-db")
        return
    
    local_db = LocalMusicBrainzDB(local_db_path)
    status = local_db.get_import_status()
    
    print_header("Local MusicBrainz Database")
    
    if not status:
        print_warning("No data imported yet")
    else:
        for entity_type, info in status.items():
            print_info(f"{entity_type}: {info.get('record_count', 0):,} records (imported {info.get('imported_at', 'unknown')})")


@analytics_app.command("compute")
def analytics_compute(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    target: str = typer.Option(
        "all",
        help="What to compute: all, artists, albums, tracks, temporal, discovery, geographic",
    ),
    no_resume: bool = typer.Option(
        False,
        "--no-resume",
        help="Recompute all entities instead of resuming from where it left off.",
    ),
) -> None:
    """Compute pre-calculated analytics from play data. Supports resuming if canceled."""
    from playback_analytics.console import create_enrichment_progress, format_time_remaining

    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = AnalyticsEngine(settings)
    resume = not no_resume

    print_header("Analytics Computation", f"Computing {target} analytics" + (" (resuming)" if resume else " (full)"))

    if target == "all":
        # Artists
        progress = create_enrichment_progress()
        task_id = None

        def update_artist_progress(stats):
            nonlocal task_id
            if task_id is None:
                task_id = progress.add_task(
                    "[1/6] Computing artist analytics...",
                    total=stats.total_items,
                    current=stats.current_entity_name,
                    eta=format_time_remaining(stats.estimated_seconds_remaining),
                )
            progress.update(
                task_id,
                completed=stats.current_item,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )

        with progress:
            artist_stats = engine.compute_artist_analytics(resume=resume, progress_callback=update_artist_progress)

        # Albums
        progress = create_enrichment_progress()
        task_id = None

        def update_album_progress(stats):
            nonlocal task_id
            if task_id is None:
                task_id = progress.add_task(
                    "[2/6] Computing album analytics...",
                    total=stats.total_items,
                    current=stats.current_entity_name,
                    eta=format_time_remaining(stats.estimated_seconds_remaining),
                )
            progress.update(
                task_id,
                completed=stats.current_item,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )

        with progress:
            album_stats = engine.compute_album_analytics(resume=resume, progress_callback=update_album_progress)

        # Tracks
        progress = create_enrichment_progress()
        task_id = None

        def update_track_progress(stats):
            nonlocal task_id
            if task_id is None:
                task_id = progress.add_task(
                    "[3/6] Computing track analytics...",
                    total=stats.total_items,
                    current=stats.current_entity_name,
                    eta=format_time_remaining(stats.estimated_seconds_remaining),
                )
            progress.update(
                task_id,
                completed=stats.current_item,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )

        with progress:
            track_stats = engine.compute_track_analytics(resume=resume, progress_callback=update_track_progress)

        # Temporal (quick, no entity progress needed)
        with create_progress() as progress:
            task = progress.add_task("[4/6] Computing temporal analytics...", total=None)
            temporal_stats = engine.compute_temporal_analytics()
            progress.update(task, completed=True)

        # Discovery (quick, no entity progress needed)
        with create_progress() as progress:
            task = progress.add_task("[5/6] Computing discovery context...", total=None)
            discovery_stats = engine.compute_discovery_context()
            progress.update(task, completed=True)

        # Geographic (quick, no entity progress needed)
        with create_progress() as progress:
            task = progress.add_task("[6/6] Computing geographic analytics...", total=None)
            geo_stats = engine.compute_geographic_analytics()
            progress.update(task, completed=True)

        print_summary_table("Artist Analytics", artist_stats)
        print_summary_table("Album Analytics", album_stats)
        print_summary_table("Track Analytics", track_stats)
        print_summary_table("Temporal Analytics", temporal_stats)
        print_summary_table("Discovery Analytics", discovery_stats)
        print_summary_table("Geographic Analytics", geo_stats)
    else:
        progress = create_enrichment_progress()
        task_id = None

        def update_single_progress(stats):
            nonlocal task_id
            if task_id is None:
                task_id = progress.add_task(
                    f"Computing {target} analytics...",
                    total=stats.total_items,
                    current=stats.current_entity_name,
                    eta=format_time_remaining(stats.estimated_seconds_remaining),
                )
            progress.update(
                task_id,
                completed=stats.current_item,
                current=stats.current_entity_name,
                eta=format_time_remaining(stats.estimated_seconds_remaining),
            )

        if target == "artists":
            with progress:
                stats = engine.compute_artist_analytics(resume=resume, progress_callback=update_single_progress)
        elif target == "albums":
            with progress:
                stats = engine.compute_album_analytics(resume=resume, progress_callback=update_single_progress)
        elif target == "tracks":
            with progress:
                stats = engine.compute_track_analytics(resume=resume, progress_callback=update_single_progress)
        elif target == "temporal":
            with create_progress() as prog:
                task = prog.add_task("Computing temporal analytics...", total=None)
                stats = engine.compute_temporal_analytics()
                prog.update(task, completed=True)
        elif target == "discovery":
            with create_progress() as prog:
                task = prog.add_task("Computing discovery context...", total=None)
                stats = engine.compute_discovery_context()
                prog.update(task, completed=True)
        elif target == "geographic":
            with create_progress() as prog:
                task = prog.add_task("Computing geographic analytics...", total=None)
                stats = engine.compute_geographic_analytics()
                prog.update(task, completed=True)
        else:
            typer.echo(f"Unknown target: {target}", err=True)
            raise typer.Exit(1)

        print_summary_table(f"{target.title()} Analytics", stats)


@analytics_app.command("summary")
def analytics_summary(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Print high-level analytics summary."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = AnalyticsEngine(settings)

    with create_progress() as progress:
        task = progress.add_task("Loading analytics summary...", total=None)
        summary = engine.summary()
        progress.update(task, completed=True)

    print_header("Analytics Summary")
    print_summary_table("Overview", summary)


@analytics_app.command("export")
def analytics_export(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    output: Path = typer.Option(
        Path("./analytics_export"),
        help="Output directory for JSON files.",
    ),
) -> None:
    """Export pre-computed analytics as JSON files for dashboard."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    engine = AnalyticsEngine(settings)
    exported = engine.export_json(output)
    typer.echo(f"Exported {len(exported)} files to {output}")
    for name, path in exported.items():
        typer.echo(f"  {name}: {path}")


# =============================================================================
# Ingest subcommands
# =============================================================================


@ingest_app.command("spotify")
def ingest_spotify_cmd(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    path: Optional[Path] = typer.Option(None, help="Override Spotify export path from config."),
    dry_run: bool = typer.Option(False, help="Parse files without writing to database."),
) -> None:
    """Ingest Spotify Extended Streaming History exports."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Spotify Ingestion", "Processing Extended Streaming History")

    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    runner.apply_pending()

    ingestor = SpotifyIngestor(settings)
    with create_progress() as progress:
        task = progress.add_task("Ingesting Spotify data...", total=None)
        stats = ingestor.ingest(show_progress=False, dry_run=dry_run)
        progress.update(task, completed=True)

    print_summary_table("Spotify Ingestion Results", stats.to_summary())
    if dry_run:
        print_warning("Dry run - no data written")


@ingest_app.command("lastfm")
def ingest_lastfm_cmd(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    path: Optional[Path] = typer.Option(None, help="Override Last.fm export path from config."),
    dry_run: bool = typer.Option(False, help="Parse files without writing to database."),
) -> None:
    """Ingest Last.fm CSV exports."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Last.fm Ingestion", "Processing scrobble history")

    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    runner.apply_pending()

    ingestor = LastFMIngestor(settings)
    with create_progress() as progress:
        task = progress.add_task("Ingesting Last.fm data...", total=None)
        stats = ingestor.ingest(show_progress=False, dry_run=dry_run)
        progress.update(task, completed=True)

    print_summary_table("Last.fm Ingestion Results", stats.to_summary())
    if dry_run:
        print_warning("Dry run - no data written")


# =============================================================================
# Pipeline orchestration commands
# =============================================================================


@pipeline_app.command("full")
def pipeline_full(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    skip_enrich: bool = typer.Option(False, help="Skip MusicBrainz enrichment (slow)."),
    enrich_limit: int = typer.Option(50, help="Max entities to enrich per category."),
    export_path: Optional[Path] = typer.Option(None, help="Export analytics JSON to this directory."),
) -> None:
    """Run the complete pipeline: ingest → normalize → dedupe → enrich → analytics."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)
    results = {}

    print_header("Full Pipeline", "Running complete data processing pipeline")
    total_steps = 6 if not skip_enrich else 5

    # Step 1: Initialize database
    print_step(1, total_steps, "Initializing database...")
    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    applied = runner.apply_pending()
    if applied:
        print_success(f"Applied {len(applied)} migrations")
    else:
        print_info("Database already up to date")

    # Step 2: Ingest all sources
    print_step(2, total_steps, "Ingesting source data...")
    ingest_stats = {}

    spotify_ingestor = SpotifyIngestor(settings)
    try:
        stats = spotify_ingestor.ingest(show_progress=False, dry_run=False)
        ingest_stats["spotify"] = stats.to_summary()
        print_success(f"Spotify: {stats.rows_inserted} plays ingested")
    except Exception as e:
        print_warning(f"Spotify ingestion skipped: {e}")

    lastfm_ingestor = LastFMIngestor(settings)
    try:
        stats = lastfm_ingestor.ingest(show_progress=False, dry_run=False)
        ingest_stats["lastfm"] = stats.to_summary()
        print_success(f"Last.fm: {stats.rows_inserted} plays ingested")
    except Exception as e:
        print_warning(f"Last.fm ingestion skipped: {e}")

    results["ingest"] = ingest_stats

    # Step 3: Normalization
    print_step(3, total_steps, "Running normalization...")
    norm_engine = NormalizationEngine(settings)
    norm_stats = norm_engine.process_all(dry_run=False)
    results["normalize"] = norm_stats
    print_success(
        f"Normalized: {norm_stats.get('artists', {}).get('created', 0)} artists, "
        f"{norm_stats.get('albums', {}).get('created', 0)} albums, "
        f"{norm_stats.get('tracks', {}).get('created', 0)} tracks"
    )

    # Step 4: Deduplication
    print_step(4, total_steps, "Running deduplication...")
    dedupe_engine = DeduplicationEngine(settings)
    dedupe_stats = dedupe_engine.run(dry_run=False)
    results["dedupe"] = dedupe_stats
    print_success(
        f"Deduplication: {dedupe_stats.get('duplicates_merged', 0)} merged, "
        f"{dedupe_stats.get('flagged_for_review', 0)} flagged for review"
    )

    # Step 5: Enrichment (optional)
    current_step = 5
    if not skip_enrich:
        print_step(current_step, total_steps, "Running MusicBrainz enrichment...")
        enricher = MusicBrainzEnricher(settings)
        enrich_stats = enricher.enrich_all(dry_run=False, limit=enrich_limit)
        results["enrich"] = enrich_stats
        print_success(f"Enriched: {enrich_stats.get('artists', {}).get('artists_enriched', 0)} artists")
        current_step += 1

    # Step 6: Analytics
    print_step(current_step, total_steps, "Computing analytics...")
    analytics_engine = AnalyticsEngine(settings)
    analytics_stats = analytics_engine.compute_all()
    results["analytics"] = analytics_stats
    print_success(
        f"Analytics: {analytics_stats.get('artists', {}).get('artists_computed', 0)} artists, "
        f"{analytics_stats.get('tracks', {}).get('tracks_computed', 0)} tracks"
    )

    # Export if requested
    if export_path:
        print_info(f"Exporting analytics to {export_path}...")
        exported = analytics_engine.export_json(export_path)
        print_success(f"Exported {len(exported)} files")

    # Final summary
    print_pipeline_summary(results)


@pipeline_app.command("incremental")
def pipeline_incremental(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    skip_enrich: bool = typer.Option(False, help="Skip MusicBrainz enrichment."),
    enrich_limit: int = typer.Option(20, help="Max new entities to enrich."),
) -> None:
    """Run incremental update: detect and process only new data."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Incremental Pipeline", "Processing new data only")

    # Ensure migrations are current
    runner = MigrationRunner(settings.paths.database_path, MIGRATIONS_DIR)
    runner.apply_pending()

    # Get current counts for comparison
    with connect(settings.paths.database_path) as db:
        before_plays = db.execute("SELECT COUNT(*) FROM plays").fetchone()[0]

    # Ingest new data
    print_step(1, 4, "Checking for new source data...")
    new_plays = 0

    try:
        spotify = SpotifyIngestor(settings)
        stats = spotify.ingest(show_progress=False, dry_run=False)
        new_plays += stats.rows_inserted
    except Exception:
        pass

    try:
        lastfm = LastFMIngestor(settings)
        stats = lastfm.ingest(show_progress=False, dry_run=False)
        new_plays += stats.rows_inserted
    except Exception:
        pass

    if new_plays == 0:
        print_info("No new plays detected")
        return

    print_success(f"Found {new_plays} new plays")

    # Normalize new entities
    print_step(2, 4, "Normalizing new entities...")
    norm_engine = NormalizationEngine(settings)
    norm_stats = norm_engine.process_all(dry_run=False)
    new_artists = norm_stats.get("artists", {}).get("created", 0)
    print_success(f"Created {new_artists} new canonical artists")

    # Dedupe new plays
    print_step(3, 4, "Deduplicating new plays...")
    dedupe_engine = DeduplicationEngine(settings)
    dedupe_stats = dedupe_engine.run(dry_run=False)
    print_success(f"Merged {dedupe_stats.get('duplicates_merged', 0)} duplicates")

    # Enrich new entities
    if not skip_enrich and new_artists > 0:
        print_step(4, 4, "Enriching new entities...")
        enricher = MusicBrainzEnricher(settings)
        enricher.enrich_artists(dry_run=False, limit=enrich_limit)
        print_success("Enrichment complete")
    else:
        print_step(4, 4, "Skipping enrichment")

    # Recompute analytics
    print_info("Recomputing analytics...")
    analytics = AnalyticsEngine(settings)
    analytics.compute_all()
    print_success("Analytics updated")

    # Summary
    with connect(settings.paths.database_path) as db:
        after_plays = db.execute("SELECT COUNT(*) FROM plays").fetchone()[0]

    console.print("\n[bold green]Incremental update complete[/bold green]")
    console.print(f"  New plays added: {format_number(after_plays - before_plays)}")


# =============================================================================
# Database management commands
# =============================================================================


@db_app.command("init")
def db_init(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Initialize the database with all migrations."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Database Initialization")

    db_path = settings.paths.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    runner = MigrationRunner(db_path, MIGRATIONS_DIR)
    applied = runner.apply_pending()

    if applied:
        print_success(f"Applied {len(applied)} migrations")
        for m in applied:
            console.print(f"  [dim]•[/dim] {m}")
    else:
        print_info("Database already initialized")


@db_app.command("reset")
def db_reset(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Reset the database by deleting and recreating it."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    db_path = settings.paths.database_path

    if not force:
        if not confirm_action(f"This will DELETE all data in {db_path}. Continue?"):
            print_info("Cancelled")
            raise typer.Exit(0)

    if db_path.exists():
        db_path.unlink()
        print_success(f"Deleted {db_path}")

    runner = MigrationRunner(db_path, MIGRATIONS_DIR)
    runner.apply_pending()
    print_success("Database recreated")


@db_app.command("backup")
def db_backup(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    output: Optional[Path] = typer.Option(None, help="Backup destination path."),
) -> None:
    """Create a backup of the database."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    db_path = settings.paths.database_path
    if not db_path.exists():
        print_error("Database does not exist")
        raise typer.Exit(1)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    if output is None:
        output = db_path.parent / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"

    shutil.copy2(db_path, output)
    print_success(f"Backup created: {output}")


@db_app.command("stats")
def db_stats(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Display database statistics."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    db_path = settings.paths.database_path
    if not db_path.exists():
        print_error("Database does not exist")
        raise typer.Exit(1)

    print_header("Database Statistics")

    with connect(db_path) as db:
        stats = {
            "Total plays": db.execute("SELECT COUNT(*) FROM plays").fetchone()[0],
            "Non-duplicate plays": db.execute(
                "SELECT COUNT(*) FROM plays WHERE is_duplicate = 0"
            ).fetchone()[0],
            "Canonical artists": db.execute("SELECT COUNT(*) FROM canonical_artists").fetchone()[0],
            "Canonical albums": db.execute("SELECT COUNT(*) FROM canonical_albums").fetchone()[0],
            "Canonical tracks": db.execute("SELECT COUNT(*) FROM canonical_tracks").fetchone()[0],
        }

        sources = db.execute(
            "SELECT source_name, COUNT(*) as c FROM plays GROUP BY source_name"
        ).fetchall()

        date_range = db.execute(
            "SELECT MIN(play_timestamp_utc), MAX(play_timestamp_utc) FROM plays"
        ).fetchone()

    print_summary_table("Record Counts", {k: format_number(v) for k, v in stats.items()})

    if sources:
        console.print("\n[bold]Plays by Source:[/bold]")
        for row in sources:
            console.print(f"  {row['source_name']}: {format_number(row['c'])}")

    if date_range[0]:
        console.print(f"\n[bold]Date Range:[/bold] {date_range[0][:10]} to {date_range[1][:10]}")

    # File size
    size_mb = db_path.stat().st_size / (1024 * 1024)
    console.print(f"[bold]Database Size:[/bold] {size_mb:.2f} MB")


# =============================================================================
# Configuration commands
# =============================================================================


@config_app.command("show")
def config_show(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Display current configuration."""
    settings = load_settings(config)

    print_header("Current Configuration", str(config))

    console.print("\n[bold]Paths:[/bold]")
    console.print(f"  Database: {settings.paths.database_path}")
    console.print(f"  Spotify exports: {settings.paths.raw_spotify_history}")
    console.print(f"  Last.fm exports: {settings.paths.raw_lastfm_exports}")

    console.print("\n[bold]Metadata:[/bold]")
    console.print(f"  Log level: {settings.metadata.log_level}")

    console.print(f"\n[dim]Config file: {config}[/dim]")


@config_app.command("validate")
def config_validate(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Validate configuration and check paths."""
    try:
        settings = load_settings(config)
    except Exception as e:
        print_error(f"Invalid configuration: {e}")
        raise typer.Exit(1)

    print_header("Configuration Validation")
    all_valid = True

    # Check paths
    if settings.paths.raw_spotify_history.exists():
        files = list(settings.paths.raw_spotify_history.glob("*.json"))
        print_success(f"Spotify path exists ({len(files)} JSON files)")
    else:
        print_warning(f"Spotify path does not exist: {settings.paths.raw_spotify_history}")
        all_valid = False

    if settings.paths.raw_lastfm_exports.exists():
        files = list(settings.paths.raw_lastfm_exports.glob("*.csv"))
        print_success(f"Last.fm path exists ({len(files)} CSV files)")
    else:
        print_warning(f"Last.fm path does not exist: {settings.paths.raw_lastfm_exports}")
        all_valid = False

    # Check database
    if settings.paths.database_path.exists():
        print_success(f"Database exists: {settings.paths.database_path}")
    else:
        print_info(f"Database will be created at: {settings.paths.database_path}")

    if all_valid:
        print_success("\nConfiguration is valid")
    else:
        print_warning("\nSome paths are missing - ingestion may fail")


# =============================================================================
# Review workflow commands
# =============================================================================


@review_app.command("export")
def review_export(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    output: Path = typer.Option(Path("review_queue.yaml"), help="Output file for review items."),
    include_dedupe: bool = typer.Option(True, help="Include deduplication review items."),
    include_normalize: bool = typer.Option(True, help="Include normalization ambiguities."),
) -> None:
    """Export items needing human review to a YAML file."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Export Review Queue")
    review_data = {"exported_at": datetime.now(UTC).isoformat(), "items": []}

    if include_dedupe:
        # Get pending review items from dedupe_review_queue
        with connect(settings.paths.database_path) as db:
            pending = db.execute(
                """
                SELECT drq.*, 
                       p1.play_timestamp_utc as play_a_time,
                       p2.play_timestamp_utc as play_b_time
                FROM dedupe_review_queue drq
                JOIN plays p1 ON drq.play_a_id = p1.id
                JOIN plays p2 ON drq.play_b_id = p2.id
                WHERE drq.resolved = 0
                ORDER BY drq.confidence DESC
                LIMIT 100
                """
            ).fetchall()

        for row in pending:
            review_data["items"].append({
                "type": "deduplication",
                "play_a_id": row["play_a_id"],
                "play_b_id": row["play_b_id"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "decision": None,  # User fills this in
            })

        print_success(f"Found {len(pending)} deduplication items for review")

    if include_normalize:
        norm_engine = NormalizationEngine(settings)
        norm_engine.process_all(dry_run=True, fuzzy_threshold=0.85)
        # The ambiguous matches would be collected during dry run
        print_info("Normalization review items collected")

    with output.open("w") as f:
        yaml.dump(review_data, f, default_flow_style=False, allow_unicode=True)

    print_success(f"Review queue exported to {output}")
    console.print("\n[dim]Edit the file and use 'review import' to apply decisions[/dim]")


@review_app.command("import")
def review_import(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
    input_file: Path = typer.Option(
        Path("review_queue.yaml"),
        "--input", "-i",
        exists=True,
        readable=True,
        help="Review file with decisions.",
    ),
) -> None:
    """Import human review decisions from a YAML file."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    print_header("Import Review Decisions")

    with input_file.open() as f:
        review_data = yaml.safe_load(f)

    if not review_data or "items" not in review_data:
        print_error("Invalid review file format")
        raise typer.Exit(1)

    applied = 0
    skipped = 0

    with connect(settings.paths.database_path) as db:
        for item in review_data["items"]:
            decision = item.get("decision")
            if not decision:
                skipped += 1
                continue

            if item["type"] == "deduplication":
                if decision == "merge":
                    # Mark play_b as duplicate of play_a
                    db.execute(
                        """
                        UPDATE plays SET is_duplicate = 1, duplicate_of_id = ?
                        WHERE id = ?
                        """,
                        (item["play_a_id"], item["play_b_id"]),
                    )
                    db.execute(
                        "UPDATE dedupe_review_queue SET resolved = 1 WHERE play_a_id = ? AND play_b_id = ?",
                        (item["play_a_id"], item["play_b_id"]),
                    )
                    applied += 1
                elif decision == "keep_both":
                    db.execute(
                        "UPDATE dedupe_review_queue SET resolved = 1 WHERE play_a_id = ? AND play_b_id = ?",
                        (item["play_a_id"], item["play_b_id"]),
                    )
                    applied += 1

    print_success(f"Applied {applied} decisions, skipped {skipped} items without decisions")


@review_app.command("status")
def review_status(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to settings TOML."),
) -> None:
    """Show pending review items count."""
    settings = load_settings(config)
    configure_logging(settings.metadata.log_level)

    with connect(settings.paths.database_path) as db:
        dedupe_pending = db.execute(
            "SELECT COUNT(*) FROM dedupe_review_queue WHERE resolved = 0"
        ).fetchone()[0]

    print_header("Review Queue Status")
    console.print(f"  Deduplication items pending: {dedupe_pending}")

    if dedupe_pending > 0:
        console.print("\n[dim]Run 'review export' to get items for review[/dim]")


if __name__ == "__main__":
    app()
