"""Acceso al dominio de decisiones en NOBODY_BRAIN."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Decision:
    objective_id: str | None
    evidence: str
    reasoning: str
    action: str
    expected_result: str
    status: str = "executed"


def record(conn: sqlite3.Connection, decision: Decision) -> int:
    cur = conn.execute(
        """
        INSERT INTO decisions (objective_id, evidence, reasoning, action, expected_result, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            decision.objective_id, decision.evidence, decision.reasoning,
            decision.action, decision.expected_result, decision.status,
        ),
    )
    return cur.lastrowid


def recent(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM decisions ORDER BY decided_at DESC LIMIT ?", (limit,)
    ).fetchall()
