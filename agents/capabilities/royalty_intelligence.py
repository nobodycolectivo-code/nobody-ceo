"""Capability: agregaciones de inteligencia sobre royalty_facts_resolved.

Solo lee NOBODY_BRAIN — no llama a ninguna plataforma externa. Esta capa
calcula los números; brain/royalties/hero_engine.py los interpreta en
clasificaciones.

Diseño: royalty_facts_resolved es una VIEW que agrega toda la tabla raw
(GROUP BY interno). Consultarla con un WHERE isrc=? una vez por track —
necesario para el Hero Engine, que recorre cientos de tracks — recomputa
esa agregación completa en cada llamada: con ~14k filas eso pasa de
milisegundos a minutos. Por eso todo lo que necesita mirar más de un
track lee la vista UNA sola vez (load_catalogue_snapshot) y opera en
memoria sobre listas de dict — con este volumen de datos (miles de
filas, no millones) es simple y evita el problema por completo.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from brain.royalties.store import resolved_rows

NON_MARKET_COUNTRY_CODES = {"OU"}  # 'OU' = DistroKid "otro/no identificado", no es un país real
MIN_MONTHS_FOR_MOMENTUM = 3  # con menos historia, la pendiente es ruido, no señal

# Piso de revenue mensual absoluto por debajo del cual un delta_pct no es
# confiable: con catálogos de centavos (mediana real ≈ $0.016/mes-track
# activo en este catálogo), "$0.001 -> $0.002" es +100% en papel pero es
# ruido de un solo stream, no momentum real. Sin este piso, el Hero
# Engine clasificaba masivamente como RISING/DECLINING por swings de
# centavos — verificado contra datos reales antes de fijar este umbral.
MIN_MONTHLY_AVG_FOR_RELIABLE_MOMENTUM = 0.02


@dataclass
class CatalogueSnapshot:
    rows: list[dict]
    by_isrc: dict[str, list[dict]] = field(default_factory=dict)
    catalogue_months: list[str] = field(default_factory=list)


def load_catalogue_snapshot(conn: sqlite3.Connection) -> CatalogueSnapshot:
    rows = [dict(r) for r in resolved_rows(conn)]
    by_isrc: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["isrc"]:
            by_isrc[r["isrc"]].append(r)
    catalogue_months = sorted({r["sale_month"] for r in rows})
    return CatalogueSnapshot(rows=rows, by_isrc=dict(by_isrc), catalogue_months=catalogue_months)


def revenue_summary(snapshot: CatalogueSnapshot) -> dict:
    total = sum(r["earnings_usd"] for r in snapshot.rows)
    by_month: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "quantity": 0})
    for r in snapshot.rows:
        m = by_month[r["sale_month"]]
        m["revenue"] += r["earnings_usd"]
        m["quantity"] += r["quantity"]
    ordered = [{"sale_month": m, **by_month[m]} for m in sorted(by_month)]
    return {"total_usd": total, "by_month": ordered}


def top_dimension(snapshot: CatalogueSnapshot, dimension: str, limit: int = 10) -> list[dict]:
    if dimension not in {"store", "country_of_sale", "isrc", "upc"}:
        raise ValueError(f"dimensión no soportada: {dimension}")
    agg: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "quantity": 0})
    for r in snapshot.rows:
        key = r[dimension]
        agg[key]["revenue"] += r["earnings_usd"]
        agg[key]["quantity"] += r["quantity"]
    ranked = sorted(
        ({"key": k, **v} for k, v in agg.items()), key=lambda x: x["revenue"], reverse=True
    )
    return ranked[:limit]


def relevant_markets(snapshot: CatalogueSnapshot, limit: int = 10) -> list[dict]:
    """Igual que top_dimension('country_of_sale') pero excluyendo 'OU'
    (no es un mercado real, es un cajón de 'no identificado')."""
    ranked = top_dimension(snapshot, "country_of_sale", limit=len(snapshot.rows) or 1)
    ranked = [r for r in ranked if r["key"] not in NON_MARKET_COUNTRY_CODES]
    return ranked[:limit]


def track_totals(snapshot: CatalogueSnapshot) -> list[dict]:
    """Un track = un ISRC, ordenado por revenue total descendente."""
    result = []
    for isrc, rows in snapshot.by_isrc.items():
        result.append(
            {
                "isrc": isrc,
                "upc": rows[0]["upc"],
                "title": rows[0]["title"],
                "revenue_total": sum(r["earnings_usd"] for r in rows),
                "quantity_total": sum(r["quantity"] for r in rows),
            }
        )
    result.sort(key=lambda t: t["revenue_total"], reverse=True)
    return result


def concentration(snapshot: CatalogueSnapshot) -> dict:
    """Qué porcentaje del revenue total viene del Top 1/5/10 de tracks."""
    tracks = track_totals(snapshot)
    total = sum(t["revenue_total"] for t in tracks) or 1.0
    result = {}
    for n in (1, 5, 10):
        top_n_revenue = sum(t["revenue_total"] for t in tracks[:n])
        result[f"top_{n}_share"] = top_n_revenue / total
    result["track_count"] = len(tracks)
    return result


def track_series(snapshot: CatalogueSnapshot, isrc: str) -> list[dict]:
    rows = snapshot.by_isrc.get(isrc, [])
    by_month: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "quantity": 0})
    for r in rows:
        m = by_month[r["sale_month"]]
        m["revenue"] += r["earnings_usd"]
        m["quantity"] += r["quantity"]
    return [{"sale_month": m, **by_month[m]} for m in sorted(by_month)]


def _windowed_average(series_by_month: dict[str, float], months: list[str]) -> float:
    values = [series_by_month.get(m, 0.0) for m in months]
    return sum(values) / len(values) if values else 0.0


def momentum(snapshot: CatalogueSnapshot, isrc: str, window: int = 3) -> dict:
    """Compara el promedio de revenue de la ventana reciente de `window`
    meses del catálogo contra la ventana inmediatamente anterior, desde
    el primer mes en que el track tuvo revenue. Si no hay suficiente
    historia, la señal se marca no confiable en vez de inventar una
    pendiente con poca base."""
    series = track_series(snapshot, isrc)
    active_months = {r["sale_month"] for r in series if r["revenue"] > 0}
    if not active_months:
        return {"delta_pct": None, "reliable": False, "reason": "sin revenue registrado"}

    first_active_month = min(active_months)
    months_since_first = [m for m in snapshot.catalogue_months if m >= first_active_month]

    if len(months_since_first) < window + 1:
        return {
            "delta_pct": None, "reliable": False,
            "reason": f"menos de {window + 1} meses de historia desde el primer revenue",
        }

    by_month = {r["sale_month"]: r["revenue"] for r in series}
    recent_window = months_since_first[-window:]
    prior_window = months_since_first[-2 * window:-window] or months_since_first[:-window]

    recent_avg = _windowed_average(by_month, recent_window)
    prior_avg = _windowed_average(by_month, prior_window)
    recent_values = [by_month.get(m, 0.0) for m in recent_window]
    recent_sum = sum(recent_values)
    # un solo mes con un pico (p. ej. un evento puntual) puede maquillar
    # 3 meses de promedio como "momentum" — se expone para que el Hero
    # Engine pueda bajar confianza en vez de tratarlo igual que una
    # tendencia sostenida en los 3 meses.
    spike_share = (max(recent_values) / recent_sum) if recent_sum > 0 else 0.0

    if prior_avg == 0 and recent_avg == 0:
        return {"delta_pct": 0.0, "reliable": True, "recent_avg": 0.0, "prior_avg": 0.0,
                "spike_share": 0.0}

    if max(recent_avg, prior_avg) < MIN_MONTHLY_AVG_FOR_RELIABLE_MOMENTUM:
        delta_pct = (
            None if prior_avg == 0 else (recent_avg - prior_avg) / prior_avg
        )
        return {
            "delta_pct": delta_pct, "reliable": False,
            "recent_avg": recent_avg, "prior_avg": prior_avg, "spike_share": spike_share,
            "reason": "revenue mensual por debajo del piso de ruido "
                      f"(${MIN_MONTHLY_AVG_FOR_RELIABLE_MOMENTUM}/mes) para confiar en el % de cambio",
        }

    if prior_avg == 0:
        return {"delta_pct": None, "reliable": True, "recent_avg": recent_avg, "prior_avg": 0.0,
                "spike_share": spike_share,
                "reason": "empezó a generar revenue en la ventana reciente"}

    delta_pct = (recent_avg - prior_avg) / prior_avg
    return {"delta_pct": delta_pct, "reliable": True, "recent_avg": recent_avg,
            "prior_avg": prior_avg, "spike_share": spike_share}


def persistence(snapshot: CatalogueSnapshot, isrc: str, months: int = 6) -> dict:
    """Fracción de los últimos `months` meses del catálogo (no del track)
    en los que el track tuvo revenue > 0 — mide continuidad, no volumen."""
    window = snapshot.catalogue_months[-months:]
    series = track_series(snapshot, isrc)
    active = {r["sale_month"] for r in series if r["revenue"] > 0}
    hits = sum(1 for m in window if m in active)
    return {
        "months_active": hits,
        "months_window": len(window),
        "ratio": hits / len(window) if window else 0.0,
    }


def platform_diversity(snapshot: CatalogueSnapshot, isrc: str) -> dict:
    rows = snapshot.by_isrc.get(isrc, [])
    by_store: dict[str, float] = defaultdict(float)
    for r in rows:
        if r["earnings_usd"] > 0:
            by_store[r["store"]] += r["earnings_usd"]
    total = sum(by_store.values()) or 1.0
    dominant_share = max(by_store.values(), default=0.0) / total
    return {
        "platform_count": len(by_store),
        "dominant_platform_share": dominant_share,
        "stores": [{"store": k, "revenue": v} for k, v in by_store.items()],
    }


def market_diversity(snapshot: CatalogueSnapshot, isrc: str) -> dict:
    rows = snapshot.by_isrc.get(isrc, [])
    by_country: dict[str, float] = defaultdict(float)
    for r in rows:
        if r["earnings_usd"] > 0 and r["country_of_sale"] not in NON_MARKET_COUNTRY_CODES:
            by_country[r["country_of_sale"]] += r["earnings_usd"]
    return {
        "market_count": len(by_country),
        "countries": [{"country_of_sale": k, "revenue": v} for k, v in by_country.items()],
    }


def catalogue_intelligence_summary(conn: sqlite3.Connection) -> dict:
    """Resumen agregado usado por board_context() — no es por-track, es
    la vista de "todo el catálogo" que el CEO usa como contexto general."""
    snapshot = load_catalogue_snapshot(conn)
    return {
        "revenue": revenue_summary(snapshot),
        "concentration": concentration(snapshot),
        "top_stores": top_dimension(snapshot, "store", limit=5),
        "top_markets": relevant_markets(snapshot, limit=5),
        "months_covered": len(snapshot.catalogue_months),
    }
