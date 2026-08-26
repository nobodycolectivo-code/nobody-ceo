import os
import time

import pytest

import agents.capabilities.catalogue_cache as cache_module
from agents.capabilities.catalogue_cache import _prune_catalogue_cache


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "catalogue_cache"
    d.mkdir()
    monkeypatch.setattr(cache_module, "CATALOGUE_CACHE_DIR", d)
    return d


def _make_file(path, size_bytes, age_offset_seconds=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size_bytes)
    if age_offset_seconds:
        t = time.time() - age_offset_seconds
        os.utime(path, (t, t))


def test_no_pruning_when_under_cap(cache_dir):
    _make_file(cache_dir / "Album A" / "track1.wav", 1000)
    _prune_catalogue_cache(max_bytes=10_000)
    assert (cache_dir / "Album A" / "track1.wav").exists()


def test_prunes_oldest_first_across_subdirs(cache_dir):
    _make_file(cache_dir / "Album A" / "old.wav", 400, age_offset_seconds=300)
    _make_file(cache_dir / "Album B" / "new.wav", 400, age_offset_seconds=10)
    _prune_catalogue_cache(max_bytes=400)

    assert not (cache_dir / "Album A" / "old.wav").exists()
    assert (cache_dir / "Album B" / "new.wav").exists()


def test_missing_cache_dir_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CATALOGUE_CACHE_DIR", tmp_path / "does_not_exist")
    _prune_catalogue_cache(max_bytes=100)  # no debe lanzar
