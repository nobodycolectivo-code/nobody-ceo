from functools import partial

import pytest

import brain.db as db_module
from agents.capabilities.board import royalties_context
from agents.capabilities.hero_engine import run_classification
from agents.capabilities.link_royalties_catalogue import link_all
from brain.catalogue.store import Album, Track, upsert_album, upsert_track
from brain.royalties.store import RoyaltyFact, insert_facts_raw


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


def test_royalties_context_reflects_seeded_data_and_classifications():
    conn = connect()

    upsert_album(conn, Album(id="album-a", title="Album A", source_path="/x"))
    upsert_track(conn, Track(id="album-a/track-a", album_id="album-a", title="Track A", audio_path="/x/a.wav"))
    conn.commit()

    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    facts = [
        fact(isrc="ISRC-A", title="Track A", sale_month=m, earnings_usd=5.0, source_row_num=i + 1)
        for i, m in enumerate(months)
    ]
    facts += [
        fact(isrc="ISRC-B", title="Track B (no catálogo)", sale_month=m, earnings_usd=0.5,
             source_row_num=100 + i)
        for i, m in enumerate(months)
    ]
    insert_facts_raw(conn, facts)
    conn.commit()

    link_all(conn, dry_run=False)
    run_classification(conn, persist=True)

    ctx = royalties_context(conn)

    assert ctx["intelligence"]["revenue"]["total_usd"] == pytest.approx(6 * 5.5)
    assert ctx["unmatched_catalogue_count"] == 1
    assert "Track B (no catálogo)" in ctx["unmatched_catalogue_titles_sample"]
    all_titles = {
        h["title"] for bucket in ("heroes", "rising", "declining", "dormant") for h in ctx[bucket]
    }
    # Track A debería aparecer clasificado en alguna categoría con evidencia
    assert any("Track A" == h["title"] for bucket in ("heroes", "rising", "declining", "dormant",)
               for h in ctx[bucket]) or ctx["evergreen_count"] >= 1 or ctx["experiment_count"] >= 1
