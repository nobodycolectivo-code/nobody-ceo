"""Conexión y bootstrap de NOBODY_BRAIN (SQLite de un solo archivo)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "brain" / "schema.sql"

# NOBODY_DB_PATH permite apuntar a un volumen persistente (p. ej. en
# Railway) sin depender de dónde el runtime coloque el código. En local,
# por defecto, es data/nobody.db dentro del repo.
DEFAULT_DB_PATH = Path(os.environ.get("NOBODY_DB_PATH", REPO_ROOT / "data" / "nobody.db"))


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
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS no altera una tabla que ya existe — si
    una tabla ya desplegada necesita una columna nueva, hace falta un
    ALTER TABLE explícito acá, guardado con un chequeo de
    PRAGMA table_info (SQLite no tiene ADD COLUMN IF NOT EXISTS, y esto
    corre en cada connect() — sin el chequeo, la segunda ejecución
    rompería con "duplicate column name")."""
    def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    # 2026-08-26 — Creative QA Fase 1, estructura de tres actos (hook/body/cta)
    _add_column_if_missing("creative_briefs", "body", "body TEXT")
