"""Acceso al dominio de royalties (imports de DistroKid) en NOBODY_BRAIN.

Dos capas, ver brain/schema.sql para el razonamiento completo:
  - royalty_facts_raw: inmutable, una fila por línea de CSV vista.
  - royalty_facts_resolved: vista, último reporting_date por combinación
    dimensional — es la única que debe consultar el resto del sistema.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, fields


@dataclass
class RoyaltyFact:
    source_file: str
    source_row_num: int
    date_inserted: str
    reporting_date: str
    sale_month: str
    store: str
    artist: str
    title: str
    upc: str
    quantity: int
    team_percentage: float
    source_type: str
    country_of_sale: str
    songwriter_withheld_usd: float
    earnings_usd: float
    isrc: str | None = None
    recoup_usd: float | None = None

    def row_hash(self) -> str:
        """Hash del contenido íntegro de la fila fuente del CSV (no de
        source_file/source_row_num/imported_at — esos son metadata de la
        importación, no parte del hecho reportado). Dos exports que
        contienen la misma línea de DistroKid producen el mismo hash,
        así reimportar un export solapado no duplica nada."""
        parts = [
            self.date_inserted, self.reporting_date, self.sale_month,
            self.store, self.artist, self.title, self.isrc or "",
            self.upc, str(self.quantity), str(self.team_percentage),
            self.source_type, self.country_of_sale,
            repr(self.songwriter_withheld_usd), repr(self.earnings_usd),
            "" if self.recoup_usd is None else repr(self.recoup_usd),
        ]
        digest_input = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(digest_input).hexdigest()


def insert_facts_raw(conn: sqlite3.Connection, facts: list[RoyaltyFact]) -> dict:
    """INSERT OR IGNORE por row_hash — idempotente: una fila ya vista
    (mismo contenido fuente, de este import o de uno anterior) no se
    vuelve a insertar ni se cuenta como error."""
    inserted = 0
    skipped = 0
    field_names = [f.name for f in fields(RoyaltyFact)]
    columns = ", ".join(field_names)
    placeholders = ", ".join(f":{n}" for n in field_names)
    for fact in facts:
        row_hash = fact.row_hash()
        params = {"row_hash": row_hash, **{n: getattr(fact, n) for n in field_names}}
        cur = conn.execute(
            f"""
            INSERT OR IGNORE INTO royalty_facts_raw (row_hash, {columns})
            VALUES (:row_hash, {placeholders})
            """,
            params,
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
    return {"inserted": inserted, "skipped_duplicate": skipped}


def raw_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM royalty_facts_raw").fetchone()[0]


def resolved_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM royalty_facts_resolved").fetchall()


def revenue_total(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(earnings_usd), 0) AS total FROM royalty_facts_resolved"
    ).fetchone()
    return row["total"]


def revenue_by_month(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT sale_month,
               SUM(earnings_usd) AS revenue,
               SUM(quantity) AS quantity
        FROM royalty_facts_resolved
        GROUP BY sale_month
        ORDER BY sale_month
        """
    ).fetchall()


def revenue_by_dimension(conn: sqlite3.Connection, dimension: str) -> list[sqlite3.Row]:
    """dimension: 'store' | 'country_of_sale' | 'isrc' | 'upc'."""
    if dimension not in {"store", "country_of_sale", "isrc", "upc"}:
        raise ValueError(f"dimensión no soportada: {dimension}")
    return conn.execute(
        f"""
        SELECT {dimension} AS key,
               SUM(earnings_usd) AS revenue,
               SUM(quantity) AS quantity
        FROM royalty_facts_resolved
        GROUP BY {dimension}
        ORDER BY revenue DESC
        """
    ).fetchall()


def track_monthly_series(conn: sqlite3.Connection, isrc: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT sale_month,
               SUM(earnings_usd) AS revenue,
               SUM(quantity) AS quantity
        FROM royalty_facts_resolved
        WHERE isrc = ?
        GROUP BY sale_month
        ORDER BY sale_month
        """,
        (isrc,),
    ).fetchall()


def all_sale_months(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT sale_month FROM royalty_facts_resolved ORDER BY sale_month"
    ).fetchall()
    return [r["sale_month"] for r in rows]


def distinct_tracks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Un track = un ISRC (un ISRC nunca cambia de título — verificado en
    la auditoría, así que tomar `title`/`upc` como columna suelta de un
    GROUP BY es seguro aquí). Deliberadamente NO usa una subquery
    correlacionada contra la vista: royalty_facts_resolved agrega sobre
    todo el catálogo, y una subquery correlacionada la recomputaría
    entera una vez por track (cientos de veces) — con 14k filas eso pasa
    de milisegundos a minutos. Una sola pasada agregada evita ese costo."""
    return conn.execute(
        """
        SELECT isrc, upc, title,
               SUM(earnings_usd) AS revenue_total,
               SUM(quantity) AS quantity_total
        FROM royalty_facts_resolved
        WHERE isrc IS NOT NULL
        GROUP BY isrc
        ORDER BY revenue_total DESC
        """
    ).fetchall()


# ── royalty_track_links ─────────────────────────────────────────────────

@dataclass
class RoyaltyTrackLink:
    isrc: str
    upc: str
    title: str
    match_method: str  # exact_title | fuzzy_title | unmatched
    match_confidence: float
    track_id: str | None = None
    album_id: str | None = None


def upsert_track_link(conn: sqlite3.Connection, link: RoyaltyTrackLink) -> None:
    conn.execute(
        """
        INSERT INTO royalty_track_links
            (isrc, upc, title, track_id, album_id, match_method, match_confidence)
        VALUES (:isrc, :upc, :title, :track_id, :album_id, :match_method, :match_confidence)
        ON CONFLICT(isrc) DO UPDATE SET
            upc = excluded.upc,
            title = excluded.title,
            track_id = excluded.track_id,
            album_id = excluded.album_id,
            match_method = excluded.match_method,
            match_confidence = excluded.match_confidence,
            linked_at = datetime('now')
        """,
        {
            "isrc": link.isrc, "upc": link.upc, "title": link.title,
            "track_id": link.track_id, "album_id": link.album_id,
            "match_method": link.match_method, "match_confidence": link.match_confidence,
        },
    )


def unmatched_links(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM royalty_track_links WHERE track_id IS NULL ORDER BY title"
    ).fetchall()


def link_for_isrc(conn: sqlite3.Connection, isrc: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM royalty_track_links WHERE isrc = ?", (isrc,)
    ).fetchone()


# ── hero_classifications ────────────────────────────────────────────────

@dataclass
class HeroClassification:
    isrc: str
    title: str
    classification: str
    hero_score: float
    confidence: float
    reason_codes_json: str
    supporting_metrics_json: str
    track_id: str | None = None


def record_hero_classification(conn: sqlite3.Connection, c: HeroClassification) -> int:
    cur = conn.execute(
        """
        INSERT INTO hero_classifications
            (isrc, track_id, title, classification, hero_score, confidence,
             reason_codes, supporting_metrics)
        VALUES (:isrc, :track_id, :title, :classification, :hero_score, :confidence,
                :reason_codes_json, :supporting_metrics_json)
        """,
        {
            "isrc": c.isrc, "track_id": c.track_id, "title": c.title,
            "classification": c.classification, "hero_score": c.hero_score,
            "confidence": c.confidence, "reason_codes_json": c.reason_codes_json,
            "supporting_metrics_json": c.supporting_metrics_json,
        },
    )
    return cur.lastrowid


def latest_hero_classifications(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Última clasificación por ISRC (no historial completo)."""
    return conn.execute(
        """
        SELECT h.* FROM hero_classifications h
        JOIN (
            SELECT isrc, MAX(computed_at) AS max_computed_at
            FROM hero_classifications GROUP BY isrc
        ) latest ON h.isrc = latest.isrc AND h.computed_at = latest.max_computed_at
        ORDER BY h.hero_score DESC
        """
    ).fetchall()


def latest_by_classification(conn: sqlite3.Connection, classification: str) -> list[sqlite3.Row]:
    rows = latest_hero_classifications(conn)
    return [r for r in rows if r["classification"] == classification]
