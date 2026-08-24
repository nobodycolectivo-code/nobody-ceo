from functools import partial

import pytest

import brain.db as db_module
from brain.royalties.store import RoyaltyFact, insert_facts_raw

from agents.capabilities.hero_engine import run_classification


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test_nobody.db"
    monkeypatch.setattr(db_module, "connect", partial(db_module.connect, db_path=db_path))


def connect():
    return db_module.connect()


def fact(**overrides) -> RoyaltyFact:
    base = dict(
        source_file="results.csv", source_row_num=1,
        date_inserted="2026-01-01", reporting_date="2026-01-01",
        sale_month="2026-01", store="Spotify", artist="NØBØĐ¥",
        title="Track", isrc="ISRC001", upc="UPC001", quantity=10,
        team_percentage=100.0, source_type="Song", country_of_sale="US",
        songwriter_withheld_usd=0.0, earnings_usd=1.0, recoup_usd=None,
    )
    base.update(overrides)
    return RoyaltyFact(**base)


def seed(conn, facts):
    insert_facts_raw(conn, facts)
    conn.commit()


CATALOGUE_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def by_isrc(results, isrc):
    return next(r for r in results if r["isrc"] == isrc)


def test_short_history_is_experiment():
    """Menos de 4 meses desde el primer revenue -> momentum no confiable
    -> EXPERIMENT, nunca una categoría fuerte con poca base."""
    conn = connect()
    facts = [
        fact(isrc="NEW", sale_month="2026-05", earnings_usd=5.0, source_row_num=1),
        fact(isrc="NEW", sale_month="2026-06", earnings_usd=5.0, source_row_num=2),
    ]
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "NEW")
    assert r["classification"] == "EXPERIMENT"
    assert r["confidence"] < 0.5


def test_dormant_had_revenue_but_quiet_recently():
    conn = connect()
    facts = []
    # revenue fuerte en los primeros 3 meses, nada en los últimos 3
    for i, m in enumerate(CATALOGUE_MONTHS[:3]):
        facts.append(fact(isrc="OLD", sale_month=m, earnings_usd=10.0, source_row_num=i + 1))
    # otro track mantiene vivos los últimos meses del catálogo
    for i, m in enumerate(CATALOGUE_MONTHS):
        facts.append(fact(isrc="FILLER", sale_month=m, earnings_usd=1.0, source_row_num=100 + i))
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "OLD")
    assert r["classification"] == "DORMANT"


def test_hero_top_decile_persistent_flat_momentum():
    conn = connect()
    facts = []
    # HERO: revenue alto y estable en los 6 meses (top del catálogo)
    for i, m in enumerate(CATALOGUE_MONTHS):
        facts.append(fact(isrc="STAR", sale_month=m, earnings_usd=20.0, source_row_num=i + 1))
    # resto del catálogo con revenue bajo, para que STAR quede en el top decile
    for j in range(12):
        for i, m in enumerate(CATALOGUE_MONTHS):
            facts.append(
                fact(isrc=f"FILLER{j}", sale_month=m, earnings_usd=0.5,
                     source_row_num=1000 + j * 10 + i)
            )
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "STAR")
    assert r["classification"] == "HERO"
    assert r["confidence"] > 0.5


def test_rising_strong_positive_momentum():
    conn = connect()
    facts = []
    for i, m in enumerate(CATALOGUE_MONTHS):
        earnings = 0.5 if i < 3 else 5.0  # crecimiento fuerte en la segunda mitad
        facts.append(fact(isrc="UP", sale_month=m, earnings_usd=earnings, source_row_num=i + 1))
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "UP")
    assert r["classification"] == "RISING"


def test_declining_strong_negative_momentum():
    conn = connect()
    facts = []
    for i, m in enumerate(CATALOGUE_MONTHS):
        earnings = 5.0 if i < 3 else 0.5  # caída fuerte en la segunda mitad
        facts.append(fact(isrc="DOWN", sale_month=m, earnings_usd=earnings, source_row_num=i + 1))
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "DOWN")
    assert r["classification"] == "DECLINING"


def test_evergreen_sustained_moderate_not_top_decile():
    conn = connect()
    facts = []
    # revenue moderado y constante, sin ser el top del catálogo
    for i, m in enumerate(CATALOGUE_MONTHS):
        facts.append(fact(isrc="STEADY", sale_month=m, earnings_usd=2.0, source_row_num=i + 1))
    # 20 tracks que superan a STEADY en revenue, para que quede claramente
    # fuera del top decile por posición de ranking (no solo por margen).
    for j in range(20):
        for i, m in enumerate(CATALOGUE_MONTHS):
            facts.append(
                fact(isrc=f"FILLER{j}", sale_month=m, earnings_usd=3.0,
                     source_row_num=1000 + j * 10 + i)
            )
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "STEADY")
    assert r["supporting_metrics"]["revenue_percentile"] < 0.90
    assert r["classification"] == "EVERGREEN"


def test_reason_codes_and_supporting_metrics_present():
    conn = connect()
    facts = [fact(isrc="X", sale_month=m, earnings_usd=1.0, source_row_num=i + 1)
             for i, m in enumerate(CATALOGUE_MONTHS)]
    seed(conn, facts)
    results = run_classification(conn, persist=False)
    r = by_isrc(results, "X")
    assert isinstance(r["reason_codes"], list) and len(r["reason_codes"]) > 0
    assert "revenue_total" in r["supporting_metrics"]
    assert "momentum" in r["supporting_metrics"]
    assert "persistence_6mo" in r["supporting_metrics"]


def test_persist_writes_hero_classifications_table():
    conn = connect()
    facts = [fact(isrc="X", sale_month=m, earnings_usd=1.0, source_row_num=i + 1)
             for i, m in enumerate(CATALOGUE_MONTHS)]
    seed(conn, facts)
    run_classification(conn, persist=True)
    row = conn.execute("SELECT * FROM hero_classifications WHERE isrc = 'X'").fetchone()
    assert row is not None
    assert row["classification"] in {
        "HERO", "RISING", "EVERGREEN", "DORMANT", "DECLINING", "EXPERIMENT",
    }
