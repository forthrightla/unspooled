"""Local MusicBrainz database from JSON dumps for fast enrichment."""

from __future__ import annotations

import json
import lzma
import re
import sqlite3
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, urlretrieve

from rich import print as rprint
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

# MusicBrainz JSON dump URLs
MB_DUMP_BASE = "https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/"
MB_DUMPS = {
    "artist": "artist.tar.xz",
    "release-group": "release-group.tar.xz",
    "recording": "recording.tar.xz",
}


def get_latest_dump_url() -> str:
    """Find the latest dump directory from the MusicBrainz server."""
    try:
        with urlopen(MB_DUMP_BASE) as response:
            html = response.read().decode("utf-8")
        # Find directories like 20260107-001001/
        dirs = re.findall(r'href="(\d{8}-\d{6})/"', html)
        if dirs:
            latest = sorted(dirs)[-1]
            return f"{MB_DUMP_BASE}{latest}/"
    except Exception as e:
        rprint(f"[yellow]Warning: Could not fetch latest dump directory: {e}[/]")
    # Fallback to base URL
    return MB_DUMP_BASE


class LocalMusicBrainzDB:
    """Local SQLite database built from MusicBrainz JSON dumps."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS mb_artists (
                    mbid TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sort_name TEXT,
                    country TEXT,
                    type TEXT,
                    disambiguation TEXT,
                    tags TEXT  -- JSON array
                );
                
                CREATE TABLE IF NOT EXISTS mb_release_groups (
                    mbid TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type TEXT,
                    first_release_date TEXT,
                    artist_credit TEXT,  -- JSON
                    tags TEXT  -- JSON array
                );
                
                CREATE TABLE IF NOT EXISTS mb_recordings (
                    mbid TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    length_ms INTEGER,
                    artist_credit TEXT,  -- JSON
                    releases TEXT  -- JSON array of release info
                );
                
                CREATE TABLE IF NOT EXISTS mb_import_status (
                    entity_type TEXT PRIMARY KEY,
                    imported_at TEXT,
                    record_count INTEGER
                );
                
                -- Indexes for fast lookups
                CREATE INDEX IF NOT EXISTS idx_artists_name ON mb_artists(name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_artists_country ON mb_artists(country);
                CREATE INDEX IF NOT EXISTS idx_rg_title ON mb_release_groups(title COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_recordings_title ON mb_recordings(title COLLATE NOCASE);
            """)

    def get_import_status(self) -> Dict[str, Any]:
        """Get status of imported dumps."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM mb_import_status").fetchall()
            return {row["entity_type"]: dict(row) for row in rows}

    def is_imported(self, entity_type: str) -> bool:
        """Check if an entity type has been imported."""
        status = self.get_import_status()
        return entity_type in status

    def import_artists(self, jsonl_path: Path) -> int:
        """Import artists from JSONL file."""
        return self._import_jsonl(
            jsonl_path,
            "artist",
            "mb_artists",
            self._transform_artist,
        )

    def import_release_groups(self, jsonl_path: Path) -> int:
        """Import release groups from JSONL file."""
        return self._import_jsonl(
            jsonl_path,
            "release-group",
            "mb_release_groups",
            self._transform_release_group,
        )

    def import_recordings(self, jsonl_path: Path) -> int:
        """Import recordings from JSONL file."""
        return self._import_jsonl(
            jsonl_path,
            "recording",
            "mb_recordings",
            self._transform_recording,
        )

    def _import_jsonl(
        self,
        archive_path: Path,
        entity_type: str,
        table_name: str,
        transform_fn,
    ) -> int:
        """Import from tar.xz archive containing JSONL files."""
        from datetime import datetime, UTC

        rprint(f"[cyan]Importing {entity_type}s from {archive_path.name}...[/]")
        
        count = 0
        batch = []
        batch_size = 10000

        with sqlite3.connect(self.db_path) as conn:
            # Clear existing data
            conn.execute(f"DELETE FROM {table_name}")
            
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("•"),
                TextColumn("{task.completed:,} records"),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(f"Importing {entity_type}s", total=None)
                
                # Handle tar.xz archives
                if archive_path.suffix == ".xz" and ".tar" in archive_path.name:
                    with tarfile.open(archive_path, "r:xz") as tar:
                        for member in tar.getmembers():
                            if member.isfile() and member.name.endswith(".json"):
                                f = tar.extractfile(member)
                                if f:
                                    for line in f:
                                        try:
                                            data = json.loads(line.decode("utf-8"))
                                            row = transform_fn(data)
                                            if row:
                                                batch.append(row)
                                                count += 1
                                            
                                            if len(batch) >= batch_size:
                                                self._insert_batch(conn, table_name, batch)
                                                batch = []
                                                progress.update(task, completed=count, description=f"Importing {entity_type}s")
                                        except (json.JSONDecodeError, UnicodeDecodeError):
                                            continue
                # Handle plain JSONL or .xz compressed JSONL
                elif archive_path.suffix == ".xz":
                    with lzma.open(archive_path, "rt", encoding="utf-8") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                row = transform_fn(data)
                                if row:
                                    batch.append(row)
                                    count += 1
                                
                                if len(batch) >= batch_size:
                                    self._insert_batch(conn, table_name, batch)
                                    batch = []
                                    progress.update(task, completed=count, description=f"Importing {entity_type}s")
                            except json.JSONDecodeError:
                                continue
                else:
                    with open(archive_path, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                row = transform_fn(data)
                                if row:
                                    batch.append(row)
                                    count += 1
                                
                                if len(batch) >= batch_size:
                                    self._insert_batch(conn, table_name, batch)
                                    batch = []
                                    progress.update(task, completed=count, description=f"Importing {entity_type}s")
                            except json.JSONDecodeError:
                                continue
                
                # Insert remaining
                if batch:
                    self._insert_batch(conn, table_name, batch)
                
                progress.update(task, completed=count)
            
            # Record import status
            conn.execute(
                """
                INSERT OR REPLACE INTO mb_import_status (entity_type, imported_at, record_count)
                VALUES (?, ?, ?)
                """,
                (entity_type, datetime.now(UTC).isoformat(), count),
            )
        
        rprint(f"[green]✓[/] Imported {count:,} {entity_type}s")
        return count

    def _insert_batch(self, conn: sqlite3.Connection, table_name: str, batch: List[tuple]) -> None:
        """Insert a batch of records."""
        if not batch:
            return
        
        placeholders = ", ".join(["?"] * len(batch[0]))
        conn.executemany(
            f"INSERT OR IGNORE INTO {table_name} VALUES ({placeholders})",
            batch,
        )
        conn.commit()

    def _transform_artist(self, data: Dict[str, Any]) -> Optional[tuple]:
        """Transform artist JSON to database row."""
        mbid = data.get("id")
        name = data.get("name")
        if not mbid or not name:
            return None
        
        tags = data.get("tags", [])
        tag_list = [{"name": t.get("name"), "count": t.get("count", 0)} for t in tags] if tags else []
        
        return (
            mbid,
            name,
            data.get("sort-name"),
            data.get("country"),
            data.get("type"),
            data.get("disambiguation"),
            json.dumps(tag_list) if tag_list else None,
        )

    def _transform_release_group(self, data: Dict[str, Any]) -> Optional[tuple]:
        """Transform release group JSON to database row."""
        mbid = data.get("id")
        title = data.get("title")
        if not mbid or not title:
            return None
        
        tags = data.get("tags", [])
        tag_list = [{"name": t.get("name"), "count": t.get("count", 0)} for t in tags] if tags else []
        
        # Extract artist credit
        artist_credit = data.get("artist-credit", [])
        
        return (
            mbid,
            title,
            data.get("primary-type"),
            data.get("first-release-date"),
            json.dumps(artist_credit) if artist_credit else None,
            json.dumps(tag_list) if tag_list else None,
        )

    def _transform_recording(self, data: Dict[str, Any]) -> Optional[tuple]:
        """Transform recording JSON to database row."""
        mbid = data.get("id")
        title = data.get("title")
        if not mbid or not title:
            return None
        
        # Extract release info for album lookup
        releases = data.get("releases", [])
        release_info = []
        for rel in releases[:5]:  # Limit to 5 releases
            rg = rel.get("release-group", {})
            release_info.append({
                "release_mbid": rel.get("id"),
                "release_title": rel.get("title"),
                "release_group_mbid": rg.get("id"),
                "release_group_title": rg.get("title"),
                "date": rel.get("date"),
            })
        
        return (
            mbid,
            title,
            data.get("length"),
            json.dumps(data.get("artist-credit", [])),
            json.dumps(release_info) if release_info else None,
        )

    # Lookup methods
    def find_artist(self, name: str) -> Optional[Dict[str, Any]]:
        """Find artist by name (case-insensitive)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mb_artists WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()
            if row:
                return self._row_to_artist(row)
        return None

    def find_artist_fuzzy(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find artists with similar names."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Simple LIKE search - for better fuzzy matching, consider FTS5
            rows = conn.execute(
                "SELECT * FROM mb_artists WHERE name LIKE ? COLLATE NOCASE LIMIT ?",
                (f"%{name}%", limit),
            ).fetchall()
            return [self._row_to_artist(row) for row in rows]

    def get_artist_by_mbid(self, mbid: str) -> Optional[Dict[str, Any]]:
        """Get artist by MusicBrainz ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mb_artists WHERE mbid = ?",
                (mbid,),
            ).fetchone()
            if row:
                return self._row_to_artist(row)
        return None

    def find_release_group(self, title: str, artist_name: str = None) -> Optional[Dict[str, Any]]:
        """Find release group by title and optionally artist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if artist_name:
                row = conn.execute(
                    """
                    SELECT * FROM mb_release_groups 
                    WHERE title = ? COLLATE NOCASE 
                    AND artist_credit LIKE ? 
                    LIMIT 1
                    """,
                    (title, f"%{artist_name}%"),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM mb_release_groups WHERE title = ? COLLATE NOCASE LIMIT 1",
                    (title,),
                ).fetchone()
            if row:
                return self._row_to_release_group(row)
        return None

    def get_release_group_by_mbid(self, mbid: str) -> Optional[Dict[str, Any]]:
        """Get release group by MusicBrainz ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mb_release_groups WHERE mbid = ?",
                (mbid,),
            ).fetchone()
            if row:
                return self._row_to_release_group(row)
        return None

    def find_recording(self, title: str, artist_name: str = None) -> Optional[Dict[str, Any]]:
        """Find recording by title and optionally artist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if artist_name:
                row = conn.execute(
                    """
                    SELECT * FROM mb_recordings 
                    WHERE title = ? COLLATE NOCASE 
                    AND artist_credit LIKE ? 
                    LIMIT 1
                    """,
                    (title, f"%{artist_name}%"),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM mb_recordings WHERE title = ? COLLATE NOCASE LIMIT 1",
                    (title,),
                ).fetchone()
            if row:
                return self._row_to_recording(row)
        return None

    def _row_to_artist(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert database row to artist dict."""
        tags = json.loads(row["tags"]) if row["tags"] else []
        return {
            "id": row["mbid"],
            "name": row["name"],
            "sort-name": row["sort_name"],
            "country": row["country"],
            "type": row["type"],
            "disambiguation": row["disambiguation"],
            "tag-list": tags,
        }

    def _row_to_release_group(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert database row to release group dict."""
        tags = json.loads(row["tags"]) if row["tags"] else []
        artist_credit = json.loads(row["artist_credit"]) if row["artist_credit"] else []
        return {
            "id": row["mbid"],
            "title": row["title"],
            "primary-type": row["type"],
            "first-release-date": row["first_release_date"],
            "artist-credit": artist_credit,
            "tag-list": tags,
        }

    def _row_to_recording(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert database row to recording dict."""
        artist_credit = json.loads(row["artist_credit"]) if row["artist_credit"] else []
        releases = json.loads(row["releases"]) if row["releases"] else []
        return {
            "id": row["mbid"],
            "title": row["title"],
            "length": row["length_ms"],
            "artist-credit": artist_credit,
            "releases": releases,
        }


def download_dump(dump_type: str, output_dir: Path) -> Path:
    """Download a MusicBrainz JSON dump file."""
    if dump_type not in MB_DUMPS:
        raise ValueError(f"Unknown dump type: {dump_type}. Valid: {list(MB_DUMPS.keys())}")
    
    filename = MB_DUMPS[dump_type]
    output_path = output_dir / filename
    
    if output_path.exists():
        rprint(f"[yellow]File already exists:[/] {output_path}")
        return output_path
    
    # Find latest dump directory
    base_url = get_latest_dump_url()
    url = base_url + filename
    rprint(f"[dim]URL: {url}[/]")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rprint(f"[cyan]Downloading {filename}...[/]")
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(f"Downloading {dump_type}", total=None)
        
        def report_hook(block_num, block_size, total_size):
            if total_size > 0:
                progress.update(task, total=total_size, completed=block_num * block_size)
        
        urlretrieve(url, output_path, reporthook=report_hook)
    
    rprint(f"[green]✓[/] Downloaded to {output_path}")
    return output_path
