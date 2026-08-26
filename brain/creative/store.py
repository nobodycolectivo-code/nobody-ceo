"""Acceso al dominio de memoria creativa en NOBODY_BRAIN — Fase 1 del
Creative QA (2026-08-26). Estructura el brief de cada pieza (hook, mood,
CTA, clips buscados) y qué assets de stock se usaron, en vez de dejarlo
como texto libre en Decision.reasoning. Las fases siguientes (dedup real
entre piezas, QA automático) se construyen sobre estas tablas."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class CreativeBrief:
    content_item_id: str
    structure_json: str
    source: str  # claude | fallback
    hook: str | None = None
    mood: str | None = None
    cta: str | None = None


def record_brief(conn: sqlite3.Connection, brief: CreativeBrief) -> None:
    conn.execute(
        """
        INSERT INTO creative_briefs
            (content_item_id, hook, mood, cta, structure_json, source)
        VALUES (:content_item_id, :hook, :mood, :cta, :structure_json, :source)
        ON CONFLICT(content_item_id) DO UPDATE SET
            hook = excluded.hook, mood = excluded.mood, cta = excluded.cta,
            structure_json = excluded.structure_json, source = excluded.source
        """,
        {
            "content_item_id": brief.content_item_id, "hook": brief.hook,
            "mood": brief.mood, "cta": brief.cta,
            "structure_json": brief.structure_json, "source": brief.source,
        },
    )


def brief_for_item(conn: sqlite3.Connection, content_item_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM creative_briefs WHERE content_item_id = ?", (content_item_id,)
    ).fetchone()


@dataclass
class UsedAsset:
    content_item_id: str
    asset_type: str  # pexels_video
    asset_ref: str


def record_used_asset(conn: sqlite3.Connection, asset: UsedAsset) -> None:
    conn.execute(
        "INSERT INTO used_assets (content_item_id, asset_type, asset_ref) VALUES (?, ?, ?)",
        (asset.content_item_id, asset.asset_type, asset.asset_ref),
    )


def assets_for_item(conn: sqlite3.Connection, content_item_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM used_assets WHERE content_item_id = ? ORDER BY used_at",
        (content_item_id,),
    ).fetchall()


def all_used_asset_refs(conn: sqlite3.Connection, asset_type: str = "pexels_video") -> set[str]:
    """Todos los asset_ref ya usados alguna vez, sin importar en qué
    pieza — insumo para la deduplicación real (Fase 2), no usado todavía
    para bloquear nada en Fase 1."""
    rows = conn.execute(
        "SELECT DISTINCT asset_ref FROM used_assets WHERE asset_type = ?", (asset_type,)
    ).fetchall()
    return {r["asset_ref"] for r in rows}
