"""Simple migration runner that executes SQL files in lexical order."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .session import DatabaseSession

MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class MigrationRunner:
    """Applies SQL migrations stored in `migrations/` directory."""

    def __init__(self, db_path: str | Path, migrations_dir: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db = DatabaseSession(self.db_path)
        self.migrations_dir = Path(migrations_dir).expanduser().resolve()
        if not self.migrations_dir.exists():
            raise FileNotFoundError(f"Migrations directory not found: {self.migrations_dir}")

    def _list_migration_files(self) -> Iterable[Path]:
        return sorted(self.migrations_dir.glob("*.sql"))

    def _ensure_tracking_table(self) -> None:
        self.db.execute(MIGRATIONS_TABLE)

    def _schema_table_exists(self) -> bool:
        row = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
        ).fetchone()
        return row is not None

    def _applied_filenames(self, *, require_table: bool = True) -> set[str]:
        if not require_table and not self._schema_table_exists():
            return set()
        rows = self.db.execute("SELECT filename FROM schema_migrations").fetchall()
        return {row["filename"] for row in rows}

    def pending_migrations(self, *, dry_run: bool = False) -> list[str]:
        if dry_run:
            applied = self._applied_filenames(require_table=False)
        else:
            self._ensure_tracking_table()
            applied = self._applied_filenames(require_table=True)
        return [
            path.name
            for path in self._list_migration_files()
            if path.name not in applied
        ]

    def apply_pending(self) -> list[str]:
        """Apply all migrations not yet recorded in the database."""
        executed: list[str] = []
        for migration_name in self.pending_migrations():
            migration_file = self.migrations_dir / migration_name
            script = migration_file.read_text(encoding="utf-8")
            with self.db:
                self.db.executescript(script)
                self.db.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (?)",
                    (migration_name,),
                )
            executed.append(migration_name)
        return executed
