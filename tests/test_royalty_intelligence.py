from functools import partial

import pytest

import brain.db as db_module
from brain.royalties.store import RoyaltyFact, insert_facts_raw

from agents.capabilities.royalty_intelligence import (
    concentration,
    load_catalogue_snapshot,
    market_diversity,
    momentum,
    persistence,
    platform_diversity,
    relevant_markets,
)


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
        title="Track A", isrc="ISRC001", upc="UPC001", quantity=10,
        team_percentage=100.0, source_type="Song", country_of_sale="US",
        songwriter_withheld_usd=0.0, earnings_usd=1.0, recoup_usd=None,
    )
    base.update(overrides)
    return RoyaltyFact(**base)


def seed_snapshot(conn, facts):
    insert_facts_raw(conn, facts)
    conn.commit()
    return load_catalogue_snapshot(conn)


def test_concentration_top_n_shares():
    conn = connect()
    facts = [
        fact(isrc="A", title="A", earnings_usd=10.0, sale_month="2026-01"),
        fact(isrc="B", title="B", earnings_usd=5.0, sale_month="2026-01", source_row_num=2),
        fact(isrc="C", title="C", earnings_usd=3.0, sale_month="2026-01", source_row_num=3),
        fact(isrc="D", title="D", earnings_usd=1.0, sale_month="2026-01", source_row_num=4),
        fact(isrc="E", title="E", earnings_usd=1.0, sale_month="2026-01", source_row_num=5),
    ]
    snapshot = seed_snapshot(conn, facts)
    c = concentration(snapshot)
    assert c["track_count"] == 5
    assert c["top_1_share"] == pytest.approx(10 / 20)
    assert c["top_5_share"] == pytest.approx(1.0)


def test_relevant_markets_excludes_ou():
    conn = connect()
    facts = [
        fact(isrc="A", country_of_sale="US", earnings_usd=5.0),
        fact(isrc="A", country_of_sale="OU", earnings_usd=100.0, source_row_num=2),
    ]
    snapshot = seed_snapshot(conn, facts)
    markets = relevant_markets(snapshot)
    keys = [m["key"] for m in markets]
    assert "OU" not in keys
    assert "US" in keys


def test_momentum_reliable_with_enough_history():
    conn = connect()
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    facts = []
    for i, m in enumerate(months):
        earnings = 1.0 if i < 3 else 5.0
        facts.append(fact(isrc="A", sale_month=m, earnings_usd=earnings, source_row_num=i + 1))
    snapshot = seed_snapshot(conn, facts)

    m = momentum(snapshot, "A", window=3)
    assert m["reliable"] is True
    assert m["delta_pct"] == pytest.approx((5.0 - 1.0) / 1.0)


def test_momentum_unreliable_with_short_history():
    conn = connect()
    facts = [
        fact(isrc="A", sale_month="2026-01", earnings_usd=1.0),
        fact(isrc="A", sale_month="2026-02", earnings_usd=2.0, source_row_num=2),
    ]
    snapshot = seed_snapshot(conn, facts)
    m = momentum(snapshot, "A", window=3)
    assert m["reliable"] is False
    assert m["delta_pct"] is None


def test_persistence_counts_active_months_in_catalogue_window():
    conn = connect()
    catalogue_months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    other = [fact(isrc="OTHER", sale_month=m, earnings_usd=1.0, source_row_num=100 + i)
             for i, m in enumerate(catalogue_months)]
    active_months = ["2026-02", "2026-04", "2026-06"]
    a = [fact(isrc="A", sale_month=m, earnings_usd=1.0, source_row_num=200 + i)
         for i, m in enumerate(active_months)]
    snapshot = seed_snapshot(conn, other + a)

    p = persistence(snapshot, "A", months=6)
    assert p["months_window"] == 6
    assert p["months_active"] == 3
    assert p["ratio"] == pytest.approx(0.5)


def test_platform_diversity_dominant_share():
    conn = connect()
    facts = [
        fact(isrc="A", store="Spotify", earnings_usd=9.0),
        fact(isrc="A", store="TikTok", earnings_usd=1.0, source_row_num=2),
    ]
    snapshot = seed_snapshot(conn, facts)
    d = platform_diversity(snapshot, "A")
    assert d["platform_count"] == 2
    assert d["dominant_platform_share"] == pytest.approx(0.9)


def test_market_diversity_excludes_ou():
    conn = connect()
    facts = [
        fact(isrc="A", country_of_sale="US", earnings_usd=1.0),
        fact(isrc="A", country_of_sale="MX", earnings_usd=1.0, source_row_num=2),
        fact(isrc="A", country_of_sale="OU", earnings_usd=1.0, source_row_num=3),
    ]
    snapshot = seed_snapshot(conn, facts)
    d = market_diversity(snapshot, "A")
    assert d["market_count"] == 2
