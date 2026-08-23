"""Acceso al dominio de objetivos en NOBODY_BRAIN.

El baseline se congela al crear el objetivo (ver docs/OBJECTIVES.md) — no
se sobreescribe en cada sync, para que el progreso sea comparable contra
un punto fijo. seed_if_missing() por eso no actualiza un objetivo que ya
existe.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class Objective:
    id: str
    title: str
    baseline: dict
    target: dict
    deadline: str | None = None
    status: str = "active"


def seed_if_missing(conn: sqlite3.Connection, objective: Objective) -> None:
    exists = conn.execute(
        "SELECT 1 FROM objectives WHERE id = ?", (objective.id,)
    ).fetchone()
    if exists:
        return
    conn.execute(
        """
        INSERT INTO objectives (id, title, baseline_json, target_json, deadline, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            objective.id,
            objective.title,
            json.dumps(objective.baseline, ensure_ascii=False),
            json.dumps(objective.target, ensure_ascii=False),
            objective.deadline,
            objective.status,
        ),
    )


def get(conn: sqlite3.Connection, objective_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM objectives WHERE id = ?", (objective_id,)
    ).fetchone()
