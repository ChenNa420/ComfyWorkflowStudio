from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT / "database"
DEFAULT_DB = DATABASE_DIR / "studio.sqlite3"
SCHEMA_FILE = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_DB

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        schema = SCHEMA_FILE.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema)
        # Workflow packages are the durable local source of truth. If the
        # SQLite database is recreated, restore catalog rows from manifests.
        from backend.workflow.catalog import sync_catalog_to_db

        sync_catalog_to_db(self)


def row_to_dict(row: sqlite3.Row | None):
    return dict(row) if row is not None else None
