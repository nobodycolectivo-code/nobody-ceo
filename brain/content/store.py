"""Acceso al dominio de contenido (reels / videos largos) en NOBODY_BRAIN."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class ContentItem:
    id: str
    kind: str  # reel | long_video
    source_type: str  # track | album
    source_id: str
    render_path: str | None = None
    title: str | None = None
    description: str | None = None
    status: str = "draft"
    platform: str | None = None
    platform_video_id: str | None = None
    error: str | None = None
    objective_id: str | None = None


def insert(conn: sqlite3.Connection, item: ContentItem) -> None:
    conn.execute(
        """
        INSERT INTO content_items
            (id, kind, source_type, source_id, render_path, title, description,
             status, platform, platform_video_id, error, objective_id)
        VALUES
            (:id, :kind, :source_type, :source_id, :render_path, :title, :description,
             :status, :platform, :platform_video_id, :error, :objective_id)
        """,
        asdict(item),
    )


def mark_rendered(conn: sqlite3.Connection, item_id: str, render_path: str) -> None:
    conn.execute(
        "UPDATE content_items SET status = 'rendered', render_path = ? WHERE id = ?",
        (render_path, item_id),
    )


def mark_published(conn: sqlite3.Connection, item_id: str, platform_video_id: str) -> None:
    conn.execute(
        """
        UPDATE content_items
        SET status = 'published', platform = 'youtube',
            platform_video_id = ?, published_at = datetime('now')
        WHERE id = ?
        """,
        (platform_video_id, item_id),
    )


def mark_failed(conn: sqlite3.Connection, item_id: str, error: str) -> None:
    conn.execute(
        "UPDATE content_items SET status = 'failed', error = ? WHERE id = ?",
        (error, item_id),
    )


def recent(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM content_items ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def already_used_source_ids(conn: sqlite3.Connection, kind: str) -> set[str]:
    """IDs de track/album que ya tienen un content_item de este tipo que no
    haya fallado — para no generar el mismo reel/video dos veces."""
    rows = conn.execute(
        "SELECT source_id FROM content_items WHERE kind = ? AND status != 'failed'",
        (kind,),
    ).fetchall()
    return {r["source_id"] for r in rows}
