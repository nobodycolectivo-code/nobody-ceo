import os
import time

import pytest

import agents.capabilities.content as content_module
from agents.capabilities.content import _prune_stock_cache


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "stock_cache"
    d.mkdir()
    monkeypatch.setattr(content_module, "STOCK_CACHE_DIR", d)
    return d


def _make_file(path, size_bytes, age_offset_seconds=0):
    path.write_bytes(b"x" * size_bytes)
    if age_offset_seconds:
        t = time.time() - age_offset_seconds
        os.utime(path, (t, t))


def test_no_pruning_when_under_cap(cache_dir):
    _make_file(cache_dir / "a.mp4", 1000)
    _make_file(cache_dir / "b.mp4", 1000)
    _prune_stock_cache(max_bytes=10_000)
    assert (cache_dir / "a.mp4").exists()
    assert (cache_dir / "b.mp4").exists()


def test_prunes_oldest_first_until_under_cap(cache_dir):
    _make_file(cache_dir / "oldest.mp4", 400, age_offset_seconds=300)
    _make_file(cache_dir / "middle.mp4", 400, age_offset_seconds=200)
    _make_file(cache_dir / "newest.mp4", 400, age_offset_seconds=10)
    _prune_stock_cache(max_bytes=800)

    remaining = {f.name for f in cache_dir.iterdir()}
    assert "oldest.mp4" not in remaining
    assert "newest.mp4" in remaining
    total = sum(f.stat().st_size for f in cache_dir.iterdir())
    assert total <= 800


def test_missing_cache_dir_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(content_module, "STOCK_CACHE_DIR", tmp_path / "does_not_exist")
    _prune_stock_cache(max_bytes=100)  # no debe lanzar
