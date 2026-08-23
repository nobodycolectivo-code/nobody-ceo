"""Acceso al dominio de métricas (serie temporal genérica) en NOBODY_BRAIN."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class Metric:
    platform: str  # youtube | spotify | distrokid
    metric_date: str  # ISO date
    metric_name: str
    metric_value: float
    asset_id: str | None = None  # None = métrica a nivel de canal/cuenta


def record_metric(conn: sqlite3.Connection, metric: Metric) -> None:
    conn.execute(
        """
        INSERT INTO metrics (platform, asset_id, metric_date, metric_name, metric_value)
        VALUES (:platform, :asset_id, :metric_date, :metric_name, :metric_value)
        ON CONFLICT(platform, asset_id, metric_date, metric_name) DO UPDATE SET
            metric_value = excluded.metric_value,
            fetched_at = datetime('now')
        """,
        asdict(metric),
    )


def latest_by_name(conn: sqlite3.Connection, metric_name: str) -> sqlite3.Row | None:
    """Última lectura de una métrica sin importar la plataforma — útil
    para objetivos que no están atados a una sola fuente."""
    return conn.execute(
        """
        SELECT * FROM metrics
        WHERE metric_name = ? AND asset_id IS NULL
        ORDER BY metric_date DESC LIMIT 1
        """,
        (metric_name,),
    ).fetchone()


def latest(conn: sqlite3.Connection, platform: str, metric_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM metrics
        WHERE platform = ? AND metric_name = ? AND asset_id IS NULL
        ORDER BY metric_date DESC LIMIT 1
        """,
        (platform, metric_name),
    ).fetchone()


def history(conn: sqlite3.Connection, platform: str, metric_name: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM metrics
        WHERE platform = ? AND metric_name = ? AND asset_id IS NULL
        ORDER BY metric_date ASC
        """,
        (platform, metric_name),
    ).fetchall()
