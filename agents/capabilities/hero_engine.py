"""Hero Engine: clasifica cada track (ISRC) del catálogo en uno de seis
estados, con score + confidence + reason_codes + supporting_metrics —
nunca solo una etiqueta. Ver la auditoría del sprint para el razonamiento
completo detrás de cada regla.

Principio rector: no confundir popularidad histórica con momentum
actual. Un track top-decile en revenue total pero sin actividad reciente
no es HERO — es DORMANT. Un track sin suficiente historia para calcular
momentum de forma confiable nunca se fuerza a una categoría fuerte — cae
en EXPERIMENT, que es el estado por defecto ante evidencia insuficiente,
no un "sin clasificar" silencioso.

Solo lee NOBODY_BRAIN (vía royalty_intelligence) y escribe únicamente en
hero_classifications. No decide nada por sí mismo — el CEO interpreta
estas clasificaciones, no las ejecuta.
"""

from __future__ import annotations

import json
import sqlite3

from agents.capabilities.royalty_intelligence import (
    CatalogueSnapshot,
    load_catalogue_snapshot,
    market_diversity,
    momentum,
    persistence,
    platform_diversity,
    track_totals,
)
from brain.royalties.store import HeroClassification, link_for_isrc, record_hero_classification

HERO_REVENUE_PERCENTILE = 0.90
HERO_PERSISTENCE_MIN = 0.5
EVERGREEN_PERSISTENCE_MIN = 0.4
STRONG_MOMENTUM_UP = 0.30
STRONG_MOMENTUM_DOWN = -0.30
RECENT_ACTIVITY_WINDOW_MONTHS = 3
# si un solo mes aporta más de esto al total de la ventana reciente, el
# "momentum" puede ser un evento puntual (pico de un mes) y no una
# tendencia sostenida en los 3 meses — se penaliza confianza, no se
# descarta la clasificación.
SPIKE_SHARE_PENALTY_THRESHOLD = 0.70
SPIKE_SHARE_CONFIDENCE_PENALTY = 0.35


def revenue_percentiles(sorted_tracks: list[dict]) -> dict[str, float]:
    """sorted_tracks ya viene ordenado por revenue_total descendente
    (track_totals). Percentil 1.0 = el de mayor revenue del catálogo."""
    n = len(sorted_tracks)
    if n == 0:
        return {}
    if n == 1:
        return {sorted_tracks[0]["isrc"]: 1.0}
    return {t["isrc"]: 1 - (i / (n - 1)) for i, t in enumerate(sorted_tracks)}


def _diversity_score(platform: dict, market: dict) -> float:
    platform_component = min(1.0, platform["platform_count"] / 5)
    market_component = min(1.0, market["market_count"] / 10)
    return 0.5 * platform_component + 0.5 * market_component


def _normalized_momentum(delta_pct: float | None) -> float:
    if delta_pct is None:
        return 0.5  # neutral, no penaliza ni premia lo que no se puede medir
    clipped = max(-1.0, min(1.0, delta_pct))
    return (clipped + 1) / 2


def classify_track(
    snapshot: CatalogueSnapshot, track: dict, revenue_percentile: float,
) -> dict:
    isrc = track["isrc"]
    mom = momentum(snapshot, isrc)
    pers = persistence(snapshot, isrc, months=6)
    recent = persistence(snapshot, isrc, months=RECENT_ACTIVITY_WINDOW_MONTHS)
    platform = platform_diversity(snapshot, isrc)
    market = market_diversity(snapshot, isrc)

    supporting_metrics = {
        "revenue_total": track["revenue_total"],
        "quantity_total": track["quantity_total"],
        "revenue_percentile": revenue_percentile,
        "momentum": mom,
        "persistence_6mo": pers,
        "recent_activity_3mo": recent,
        "platform_diversity": platform,
        "market_diversity": market,
    }

    reason_codes: list[str] = []

    if not mom["reliable"]:
        reason_codes.append(f"unreliable_momentum: {mom.get('reason', 'sin detalle')}")
        classification = "EXPERIMENT"
        confidence = 0.25
        score = 0.3 * revenue_percentile  # algo de señal, pero degradada por falta de evidencia
        return _finalize(classification, score, confidence, reason_codes, supporting_metrics)

    if recent["months_active"] == 0 and track["revenue_total"] > 0:
        reason_codes.append(
            f"no_revenue_last_{RECENT_ACTIVITY_WINDOW_MONTHS}_months_despite_history"
        )
        classification = "DORMANT"
        confidence = 0.6 + 0.3 * min(1.0, pers["months_window"] / 6)
        score = 0.3 * revenue_percentile
        return _finalize(classification, score, confidence, reason_codes, supporting_metrics)

    delta = mom["delta_pct"]

    spike_penalty = 0.0
    if delta is not None and delta <= STRONG_MOMENTUM_DOWN:
        reason_codes.append(f"negative_momentum_{delta:.0%}")
        classification = "DECLINING"
        if mom.get("spike_share", 0.0) >= SPIKE_SHARE_PENALTY_THRESHOLD:
            reason_codes.append(f"spike_driven_single_month_share_{mom['spike_share']:.0%}")
            spike_penalty = SPIKE_SHARE_CONFIDENCE_PENALTY
    elif delta is not None and delta >= STRONG_MOMENTUM_UP:
        reason_codes.append(f"positive_momentum_{delta:.0%}")
        classification = "RISING"
        if mom.get("spike_share", 0.0) >= SPIKE_SHARE_PENALTY_THRESHOLD:
            reason_codes.append(f"spike_driven_single_month_share_{mom['spike_share']:.0%}")
            spike_penalty = SPIKE_SHARE_CONFIDENCE_PENALTY
    elif revenue_percentile >= HERO_REVENUE_PERCENTILE and pers["ratio"] >= HERO_PERSISTENCE_MIN:
        reason_codes.append("top_decile_revenue")
        reason_codes.append(f"persistent_{pers['months_active']}_of_{pers['months_window']}_months")
        classification = "HERO"
    elif pers["ratio"] >= EVERGREEN_PERSISTENCE_MIN:
        reason_codes.append(f"sustained_{pers['months_active']}_of_{pers['months_window']}_months")
        classification = "EVERGREEN"
    else:
        reason_codes.append("mixed_signal_insufficient_pattern")
        classification = "EXPERIMENT"

    diversity = _diversity_score(platform, market)
    momentum_norm = _normalized_momentum(delta)
    score = (
        0.40 * revenue_percentile
        + 0.25 * pers["ratio"]
        + 0.20 * momentum_norm
        + 0.15 * diversity
    )
    months_evidence = min(1.0, pers["months_window"] / 6)
    confidence = 0.3 + 0.4 * months_evidence + 0.3 * revenue_percentile - spike_penalty
    confidence = max(0.0, min(1.0, confidence))

    if platform["platform_count"] == 1:
        reason_codes.append("single_platform_dependency")
    if platform["dominant_platform_share"] >= 0.9 and platform["platform_count"] > 1:
        reason_codes.append(f"dominant_platform_share_{platform['dominant_platform_share']:.0%}")

    return _finalize(classification, score, confidence, reason_codes, supporting_metrics)


def _finalize(classification, score, confidence, reason_codes, supporting_metrics) -> dict:
    return {
        "classification": classification,
        "hero_score": round(score, 6),
        "confidence": round(confidence, 4),
        "reason_codes": reason_codes,
        "supporting_metrics": supporting_metrics,
    }


def run_classification(conn: sqlite3.Connection, persist: bool = True) -> list[dict]:
    snapshot = load_catalogue_snapshot(conn)
    tracks = track_totals(snapshot)
    percentiles = revenue_percentiles(tracks)

    results = []
    for track in tracks:
        isrc = track["isrc"]
        result = classify_track(snapshot, track, percentiles.get(isrc, 0.0))
        link = link_for_isrc(conn, isrc)
        track_id = link["track_id"] if link else None

        entry = {"isrc": isrc, "title": track["title"], "track_id": track_id, **result}
        results.append(entry)

        if persist:
            record_hero_classification(
                conn,
                HeroClassification(
                    isrc=isrc, title=track["title"], track_id=track_id,
                    classification=result["classification"],
                    hero_score=result["hero_score"], confidence=result["confidence"],
                    reason_codes_json=json.dumps(result["reason_codes"], ensure_ascii=False),
                    supporting_metrics_json=json.dumps(result["supporting_metrics"], ensure_ascii=False),
                ),
            )

    if persist:
        conn.commit()

    return results


if __name__ == "__main__":
    from collections import Counter

    from brain.db import connect

    _conn = connect()
    _results = run_classification(_conn)
    _conn.close()

    counts = Counter(r["classification"] for r in _results)
    print(f"{len(_results)} tracks clasificados: {dict(counts)}")
    for r in sorted(_results, key=lambda x: x["hero_score"], reverse=True)[:10]:
        print(f"  {r['classification']:12s} score={r['hero_score']:.3f} conf={r['confidence']:.2f}  {r['title']}")
