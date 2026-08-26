from functools import partial

import pytest

import brain.db as db_module
from brain.content.store import ContentItem, insert
from integrations.telegram.bot import _content_item_from_row, _cycle_summary_text


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test_nobody.db"
    monkeypatch.setattr(db_module, "connect", partial(db_module.connect, db_path=db_path))


def test_content_item_from_row_roundtrip():
    conn = db_module.connect()
    insert(
        conn,
        ContentItem(
            id="reel-1", kind="reel", source_type="track", source_id="track-1",
            title="Título", description="Desc", status="pending_review",
            render_path="render_output/reel-1.mp4",
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM content_items WHERE id = 'reel-1'").fetchone()
    item = _content_item_from_row(row)
    assert item.id == "reel-1"
    assert item.title == "Título"
    assert item.render_path == "render_output/reel-1.mp4"
    assert item.status == "pending_review"


def test_cycle_summary_reel_pending_review_line():
    result = {
        "actions": [{"kind": "reel", "id": "reel-1", "status": "pending_review", "video_id": None}],
        "after": {"subscribers": 100, "watch_hours_365d": 50},
    }
    text = _cycle_summary_text(result)
    assert "pendiente de tu aprobación" in text
    assert "youtu.be" not in text  # no debe inventar un link antes de aprobarse


def test_cycle_summary_reel_published_line_unaffected():
    result = {
        "actions": [{"kind": "long_video", "id": "long-1", "status": "published", "video_id": "abc123"}],
        "after": {"subscribers": 100, "watch_hours_365d": 50},
    }
    text = _cycle_summary_text(result)
    assert "https://youtu.be/abc123" in text
