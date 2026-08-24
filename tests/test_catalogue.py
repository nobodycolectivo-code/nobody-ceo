from functools import partial
from pathlib import Path

import pytest

import agents.capabilities.catalogue as catalogue_module
import brain.db as db_module
from agents.capabilities.catalogue import guess_genre, ingest, slugify


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test_nobody.db"
    patched_connect = partial(db_module.connect, db_path=db_path)
    monkeypatch.setattr(db_module, "connect", patched_connect)
    monkeypatch.setattr(catalogue_module, "connect", patched_connect)


def test_ingest_stores_relative_not_absolute_paths(tmp_path):
    """audio_path/artwork_path deben quedar relativos a catalogue_root —
    un path absoluto tipo D:\\...\\NOBODY solo existe en la máquina que
    hizo la ingesta, y no sirve en Railway. Ver agents.capabilities.
    catalogue_cache para cómo se resuelve la ruta relativa en cada entorno."""
    catalogue_root = tmp_path / "NOBODY"
    album_dir = catalogue_root / "Test Album"
    album_dir.mkdir(parents=True)
    (album_dir / "Track One.mp3").write_bytes(b"fake audio bytes")
    (album_dir / "cover.jpg").write_bytes(b"fake image bytes")

    ingest(catalogue_root, dry_run=False)

    conn = db_module.connect()
    track = conn.execute("SELECT * FROM tracks WHERE title = 'Track One'").fetchone()
    album = conn.execute("SELECT * FROM albums WHERE title = 'Test Album'").fetchone()
    conn.close()

    assert track["audio_path"] == "Test Album/Track One.mp3"
    assert not Path(track["audio_path"]).is_absolute()
    assert album["artwork_path"] == "Test Album/cover.jpg"
    assert album["source_path"] == str(album_dir)  # este SÍ queda absoluto (solo trazabilidad)


def test_slugify_basic():
    assert slugify("ALTIPLANO ANDINO") == "altiplano-andino"
    assert slugify("528 HZ vol 1") == "528-hz-vol-1"


def test_slugify_never_empty():
    assert slugify("   ") == "sin-nombre"
    assert slugify("###") == "sin-nombre"


def test_guess_genre_matches_keyword():
    assert guess_genre("ALTIPLANO ANDINO") == "ANDINO"
    assert guess_genre("528 HZ vol 1") == "FRECUENCIAS"
    assert guess_genre("Cumbia Hipnótica") == "CUMBIA"


def test_guess_genre_none_when_no_match():
    assert guess_genre("Sobre la Olas") is None
