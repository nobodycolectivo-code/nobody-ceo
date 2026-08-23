"""Capability: arma el contexto que el CEO usa para responder preguntas.

Solo lee NOBODY_BRAIN — no llama a ninguna plataforma externa (para eso
están los otros capabilities de sync, como agents.capabilities.metrics).
"""

from __future__ import annotations

import json
import sqlite3

from brain.catalogue.store import counts as catalogue_counts
from brain.catalogue.store import list_albums
from brain.db import connect
from brain.metrics.store import latest_by_name


def catalogue_summary(conn: sqlite3.Connection) -> dict:
    c = catalogue_counts(conn)
    genres: dict[str, int] = {}
    for album in list_albums(conn):
        g = album["genre_tag"] or "sin clasificar"
        genres[g] = genres.get(g, 0) + 1
    return {"albums": c["albums"], "tracks": c["tracks"], "genres": genres}


def objectives_status(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM objectives WHERE status = 'active' ORDER BY created_at"
    ).fetchall()
    result = []
    for row in rows:
        baseline = json.loads(row["baseline_json"])
        target = json.loads(row["target_json"])
        latest_readings = {}
        for metric_name in target.keys():
            m = latest_by_name(conn, metric_name)
            if m:
                latest_readings[metric_name] = {
                    "value": m["metric_value"],
                    "as_of": m["metric_date"],
                }
        result.append(
            {
                "id": row["id"],
                "title": row["title"],
                "baseline": baseline,
                "target": target,
                "latest": latest_readings,
            }
        )
    return result


def recent_decisions(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM decisions ORDER BY decided_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def recent_learnings(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM learnings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def content_performance(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    """Rendimiento por video individual publicado — vistas y horas de
    vista (si ya se propagaron en Analytics), ordenado por vistas. Esto
    es lo que le permite al CEO decir QUÉ pieza específica funciona,
    no solo el agregado del canal."""
    items = conn.execute(
        """
        SELECT id, kind, title, platform_video_id
        FROM content_items
        WHERE status = 'published'
        ORDER BY published_at DESC
        """
    ).fetchall()
    result = []
    for item in items:
        views = conn.execute(
            "SELECT metric_value FROM metrics WHERE asset_id = ? AND metric_name = 'views' "
            "ORDER BY metric_date DESC LIMIT 1",
            (item["id"],),
        ).fetchone()
        watch_hours = conn.execute(
            "SELECT metric_value FROM metrics WHERE asset_id = ? AND metric_name = 'watch_hours' "
            "ORDER BY metric_date DESC LIMIT 1",
            (item["id"],),
        ).fetchone()
        result.append(
            {
                "kind": item["kind"],
                "title": item["title"],
                "url": f"https://youtu.be/{item['platform_video_id']}",
                "views": views["metric_value"] if views else None,
                "watch_hours": watch_hours["metric_value"] if watch_hours else None,
            }
        )
    result.sort(key=lambda r: r["views"] or 0, reverse=True)
    return result[:limit]


def board_context() -> dict:
    conn = connect()
    context = {
        "catalogue": catalogue_summary(conn),
        "objectives": objectives_status(conn),
        "content_performance": content_performance(conn),
        "recent_decisions": recent_decisions(conn),
        "recent_learnings": recent_learnings(conn),
    }
    conn.close()
    return context
