from functools import partial

import pytest

import brain.db as db_module
from brain.content.store import (
    ContentItem,
    already_used_source_ids,
    get,
    insert,
    mark_pending_review,
    mark_rejected,
    pending_review,
)
from brain.creative.store import (
    CreativeBrief,
    UsedAsset,
    all_used_asset_refs,
    assets_for_item,
    brief_for_item,
    record_brief,
    record_used_asset,
)


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test_nobody.db"
    monkeypatch.setattr(db_module, "connect", partial(db_module.connect, db_path=db_path))


def connect():
    return db_module.connect()


def _seed_item(conn, item_id="reel-1"):
    insert(
        conn,
        ContentItem(
            id=item_id, kind="reel", source_type="track", source_id="track-1",
            title="Test Reel", status="rendered",
        ),
    )
    conn.commit()


def test_record_and_fetch_brief():
    conn = connect()
    _seed_item(conn)
    record_brief(
        conn,
        CreativeBrief(
            content_item_id="reel-1", hook="Un hook", mood="calm", cta="Suscríbete",
            structure_json='{"clip_queries": ["a", "b"]}', source="claude",
        ),
    )
    conn.commit()
    row = brief_for_item(conn, "reel-1")
    assert row["hook"] == "Un hook"
    assert row["source"] == "claude"


def test_record_brief_upsert_overwrites():
    conn = connect()
    _seed_item(conn)
    record_brief(conn, CreativeBrief(content_item_id="reel-1", hook="v1", structure_json="{}", source="claude"))
    record_brief(conn, CreativeBrief(content_item_id="reel-1", hook="v2", structure_json="{}", source="fallback"))
    conn.commit()
    row = brief_for_item(conn, "reel-1")
    assert row["hook"] == "v2"
    assert row["source"] == "fallback"


def test_used_assets_recorded_and_queryable():
    conn = connect()
    _seed_item(conn, "reel-1")
    _seed_item(conn, "reel-2")
    record_used_asset(conn, UsedAsset(content_item_id="reel-1", asset_type="pexels_video", asset_ref="12345"))
    record_used_asset(conn, UsedAsset(content_item_id="reel-2", asset_type="pexels_video", asset_ref="12345"))
    record_used_asset(conn, UsedAsset(content_item_id="reel-2", asset_type="pexels_video", asset_ref="67890"))
    conn.commit()

    assert {r["asset_ref"] for r in assets_for_item(conn, "reel-1")} == {"12345"}
    assert {r["asset_ref"] for r in assets_for_item(conn, "reel-2")} == {"12345", "67890"}
    assert all_used_asset_refs(conn) == {"12345", "67890"}


def test_pending_review_lifecycle():
    conn = connect()
    _seed_item(conn, "reel-1")
    mark_pending_review(conn, "reel-1")
    conn.commit()

    assert get(conn, "reel-1")["status"] == "pending_review"
    assert [r["id"] for r in pending_review(conn)] == ["reel-1"]

    mark_rejected(conn, "reel-1")
    conn.commit()
    assert get(conn, "reel-1")["status"] == "rejected"
    assert pending_review(conn) == []


def test_rejected_reel_is_retriable_not_permanently_blocked():
    """Un reel rechazado por criterio (no por error técnico) debe poder
    reintentarse con un brief nuevo — 'rejected' no cuenta como 'usado'
    para already_used_source_ids, a diferencia de 'published'."""
    conn = connect()
    _seed_item(conn, "reel-1")
    mark_rejected(conn, "reel-1")
    conn.commit()
    assert already_used_source_ids(conn, "reel") == set()
