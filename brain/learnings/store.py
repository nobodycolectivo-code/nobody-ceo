"""Acceso al dominio de aprendizajes en NOBODY_BRAIN."""

from __future__ import annotations

import sqlite3


def record(conn: sqlite3.Connection, summary: str, confidence: str = "low") -> None:
    conn.execute(
        "INSERT INTO learnings (summary, confidence) VALUES (?, ?)",
        (summary, confidence),
    )


def recent(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM learnings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
