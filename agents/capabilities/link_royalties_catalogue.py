"""Capability: vincula los ISRC de royalty_facts_raw con tracks/albums ya
ingeridos del catálogo local (agents.capabilities.catalogue).

Solo lee ambos dominios y escribe únicamente en royalty_track_links. Nunca
fuerza un vínculo sin evidencia — cuando no hay un match confiable, el
ISRC queda con track_id/album_id NULL y match_method='unmatched', visible
como "catálogo sin vincular" en vez de perderse silenciosamente.

Estrategia (en ese orden):
  1. Título normalizado (acentos/mayúsculas/espacios) exacto contra
     tracks.title. Si el título normalizado tiene más de un track_id
     candidato (frecuente: el mismo track existe dos veces en el
     catálogo como wav/ + mp3, ver catalogue.py) se vincula al album_id
     -- inequívoco- pero NO se elige un track_id al azar entre los
     duplicados de formato.
  2. Para lo que no matchea exacto: similitud de texto (difflib) contra
     todos los títulos del catálogo, con un umbral mínimo y penalizando
     confidence cuando el segundo mejor candidato queda muy cerca del
     primero (match ambiguo, no solo aproximado).

Uso:
    python -m agents.capabilities.link_royalties_catalogue
    python -m agents.capabilities.link_royalties_catalogue --dry-run
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from brain.db import connect
from brain.royalties.store import RoyaltyTrackLink, distinct_tracks, upsert_track_link

FUZZY_MIN_RATIO = 0.82
FUZZY_AMBIGUITY_MARGIN = 0.03  # si el 2do candidato queda a <3pp del 1ro, es ambiguo


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


@dataclass
class CatalogueTrack:
    track_id: str
    album_id: str
    title: str
    normalized_title: str


def load_catalogue_tracks(conn) -> list[CatalogueTrack]:
    rows = conn.execute("SELECT id, album_id, title FROM tracks").fetchall()
    return [
        CatalogueTrack(
            track_id=r["id"], album_id=r["album_id"], title=r["title"],
            normalized_title=normalize_title(r["title"]),
        )
        for r in rows
    ]


def build_exact_index(catalogue: list[CatalogueTrack]) -> dict[str, list[CatalogueTrack]]:
    index: dict[str, list[CatalogueTrack]] = defaultdict(list)
    for c in catalogue:
        index[c.normalized_title].append(c)
    return dict(index)


def match_title(
    normalized_title: str, exact_index: dict[str, list[CatalogueTrack]],
    catalogue: list[CatalogueTrack],
) -> tuple[str | None, str | None, str, float]:
    """Devuelve (track_id, album_id, match_method, match_confidence)."""
    candidates = exact_index.get(normalized_title)
    if candidates:
        if len(candidates) == 1:
            c = candidates[0]
            return c.track_id, c.album_id, "exact_title", 1.0
        album_ids = {c.album_id for c in candidates}
        if len(album_ids) == 1:
            return None, candidates[0].album_id, "exact_title_ambiguous_format", 0.7
        return None, None, "exact_title_ambiguous_album", 0.4

    scored = sorted(
        (
            (SequenceMatcher(None, normalized_title, c.normalized_title).ratio(), c)
            for c in catalogue
        ),
        key=lambda x: x[0], reverse=True,
    )
    if not scored or scored[0][0] < FUZZY_MIN_RATIO:
        return None, None, "unmatched", 0.0

    best_ratio, best = scored[0]
    confidence = best_ratio
    if len(scored) > 1 and (best_ratio - scored[1][0]) < FUZZY_AMBIGUITY_MARGIN:
        confidence = min(confidence, 0.6)  # candidato ganador pero ambiguo, no se descarta
    return best.track_id, best.album_id, "fuzzy_title", confidence


def link_all(conn, dry_run: bool = False) -> dict:
    catalogue = load_catalogue_tracks(conn)
    exact_index = build_exact_index(catalogue)

    tracks = distinct_tracks(conn)
    results = {"exact_title": 0, "exact_title_ambiguous_format": 0,
               "exact_title_ambiguous_album": 0, "fuzzy_title": 0, "unmatched": 0}
    detail: list[dict] = []

    for t in tracks:
        normalized = normalize_title(t["title"])
        track_id, album_id, method, confidence = match_title(normalized, exact_index, catalogue)
        results[method] += 1
        detail.append({
            "isrc": t["isrc"], "title": t["title"], "method": method,
            "confidence": round(confidence, 3), "track_id": track_id, "album_id": album_id,
        })
        if not dry_run:
            upsert_track_link(
                conn,
                RoyaltyTrackLink(
                    isrc=t["isrc"], upc=t["upc"], title=t["title"],
                    track_id=track_id, album_id=album_id,
                    match_method=method, match_confidence=confidence,
                ),
            )

    if not dry_run:
        conn.commit()

    return {
        "total_isrc": len(tracks),
        "by_method": results,
        "unmatched_titles": [d["title"] for d in detail if d["method"] == "unmatched"],
        "detail": detail,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vincula ISRC de royalties con tracks/albums del catálogo local"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = connect()
    report = link_all(conn, dry_run=args.dry_run)
    conn.close()

    import json

    print(json.dumps(
        {k: v for k, v in report.items() if k != "detail"}, indent=2, ensure_ascii=False
    ))
    print(f"\n{report['total_isrc']} ISRC procesados. Por método: {report['by_method']}")


if __name__ == "__main__":
    main()
