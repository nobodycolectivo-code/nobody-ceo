from pathlib import Path

import pytest

import agents.capabilities.catalogue_cache as cache_module
from agents.capabilities.catalogue_cache import resolve_catalogue_file


@pytest.fixture(autouse=True)
def _isolated_cache_dir(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(cache_module, "CATALOGUE_CACHE_DIR", cache_dir)
    return cache_dir


def test_none_input_returns_none():
    assert resolve_catalogue_file(None) is None


def test_returns_cached_path_if_already_downloaded(monkeypatch, tmp_path, _isolated_cache_dir):
    cached_file = _isolated_cache_dir / "album/track.wav"
    cached_file.parent.mkdir(parents=True)
    cached_file.write_bytes(b"fake audio")

    def _boom(*a, **kw):
        raise AssertionError("no debería intentar descargar de R2 si ya está cacheado")

    monkeypatch.setattr("integrations.r2.client.download_file", _boom)
    result = resolve_catalogue_file("album/track.wav")
    assert result == str(cached_file)


def test_uses_local_root_when_available(monkeypatch, tmp_path):
    local_root = tmp_path / "NOBODY"
    (local_root / "album").mkdir(parents=True)
    real_file = local_root / "album" / "track.wav"
    real_file.write_bytes(b"real audio")
    monkeypatch.setenv("NOBODY_CATALOGUE_ROOT", str(local_root))

    def _boom(*a, **kw):
        raise AssertionError("no debería descargar de R2 si el archivo local existe")

    monkeypatch.setattr("integrations.r2.client.download_file", _boom)
    result = resolve_catalogue_file("album/track.wav")
    assert result == str(real_file)


def test_falls_back_to_r2_download_when_no_local_copy(monkeypatch, tmp_path, _isolated_cache_dir):
    monkeypatch.delenv("NOBODY_CATALOGUE_ROOT", raising=False)

    downloaded = []

    def fake_download(key, local_path):
        downloaded.append((key, local_path))
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"from r2")

    monkeypatch.setattr("integrations.r2.client.download_file", fake_download)
    result = resolve_catalogue_file("album/track.wav")

    assert downloaded == [("album/track.wav", _isolated_cache_dir / "album/track.wav")]
    assert result == str(_isolated_cache_dir / "album/track.wav")
    assert Path(result).read_bytes() == b"from r2"
