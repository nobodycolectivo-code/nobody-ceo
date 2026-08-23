"""Conexión y bootstrap de NOBODY_BRAIN (SQLite de un solo archivo)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "brain" / "schema.sql"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "nobody.db"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Abre (o crea) la base y aplica el esquema si hace falta."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
