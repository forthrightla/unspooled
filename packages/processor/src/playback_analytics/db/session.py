"""SQLite session helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DatabaseSession:
    """Lightweight wrapper around sqlite3 with sane defaults."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.connection: sqlite3.Connection | None = None

    def _ensure_connection(self) -> sqlite3.Connection:
        if self.connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                isolation_level=None,  # autocommit, we manage transactions manually
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self.connection = conn
        return self.connection

    def cursor(self) -> sqlite3.Cursor:
        return self._ensure_connection().cursor()

    def execute(self, sql: str, parameters: tuple | dict | None = None) -> sqlite3.Cursor:
        cur = self.cursor()
        if parameters is None:
            cur.execute(sql)
        else:
            cur.execute(sql, parameters)
        return cur

    def executemany(self, sql: str, seq_of_parameters) -> sqlite3.Cursor:  # type: ignore[override]
        cur = self.cursor()
        cur.executemany(sql, seq_of_parameters)
        return cur

    def executescript(self, script: str) -> None:
        self._ensure_connection().executescript(script)

    def commit(self) -> None:
        if self.connection:
            self.connection.commit()

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "DatabaseSession":
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc:
            if self.connection:
                self.connection.rollback()
        else:
            self.commit()
        self.close()


def connect(db_path: str | Path) -> DatabaseSession:
    """Convenience factory."""
    return DatabaseSession(db_path)
