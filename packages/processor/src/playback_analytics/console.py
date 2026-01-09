"""Rich console utilities for beautiful CLI output."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

console = Console()
error_console = Console(stderr=True)


def print_header(title: str, subtitle: str = None) -> None:
    """Print a styled header."""
    text = Text(title, style="bold blue")
    if subtitle:
        text.append(f"\n{subtitle}", style="dim")
    console.print(Panel(text, border_style="blue"))


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    error_console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_step(step: int, total: int, message: str) -> None:
    """Print a pipeline step indicator."""
    console.print(f"[bold cyan][{step}/{total}][/bold cyan] {message}")


@contextmanager
def progress_context(description: str = "Processing") -> Iterator[Progress]:
    """Context manager for progress bars."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        yield progress


def create_progress() -> Progress:
    """Create a progress bar instance."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def print_summary_table(title: str, data: Dict[str, Any], style: str = "cyan") -> None:
    """Print a summary table from a dictionary."""
    table = Table(title=title, show_header=True, header_style=f"bold {style}")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    for key, value in data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                table.add_row(f"  {sub_key}", str(sub_value))
        else:
            display_key = key.replace("_", " ").title()
            table.add_row(display_key, str(value))

    console.print(table)


def print_stats_table(title: str, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    """Print a table with multiple rows."""
    table = Table(title=title, show_header=True, header_style="bold cyan")

    for col in columns:
        justify = "right" if col in ("plays", "count", "total", "duration") else "left"
        table.add_column(col.replace("_", " ").title(), justify=justify)

    for row in rows:
        table.add_row(*[str(row.get(col, "")) for col in columns])

    console.print(table)


def print_pipeline_summary(results: Dict[str, Any]) -> None:
    """Print a comprehensive pipeline summary."""
    console.print()
    console.print(Panel("[bold green]Pipeline Complete[/bold green]", border_style="green"))

    if "ingest" in results:
        print_summary_table("Ingestion", results["ingest"], "blue")

    if "normalize" in results:
        print_summary_table("Normalization", results["normalize"], "yellow")

    if "dedupe" in results:
        print_summary_table("Deduplication", results["dedupe"], "magenta")

    if "enrich" in results:
        print_summary_table("Enrichment", results["enrich"], "cyan")

    if "analytics" in results:
        print_summary_table("Analytics", results["analytics"], "green")


def confirm_action(message: str, default: bool = False) -> bool:
    """Prompt user for confirmation."""
    suffix = " [Y/n]" if default else " [y/N]"
    response = console.input(f"[yellow]?[/yellow] {message}{suffix} ")
    if not response:
        return default
    return response.lower() in ("y", "yes")


def print_file_list(title: str, files: List[str], max_show: int = 10) -> None:
    """Print a list of files."""
    console.print(f"\n[bold]{title}[/bold]")
    for i, f in enumerate(files[:max_show]):
        console.print(f"  [dim]•[/dim] {f}")
    if len(files) > max_show:
        console.print(f"  [dim]... and {len(files) - max_show} more[/dim]")


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    seconds = ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes % 60}m"
    elif minutes > 0:
        return f"{minutes}m {seconds % 60}s"
    else:
        return f"{seconds}s"


def format_number(n: int) -> str:
    """Format a number with thousands separators."""
    return f"{n:,}"


def format_time_remaining(seconds: float) -> str:
    """Format seconds as human-readable time remaining."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def create_enrichment_progress() -> Progress:
    """Create a progress bar for enrichment with time estimates."""
    from rich.progress import TimeRemainingColumn
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TextColumn("[cyan]{task.fields[current]}[/cyan]"),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TextColumn("[yellow]~{task.fields[eta]}[/yellow]"),
        console=console,
        refresh_per_second=2,
    )
