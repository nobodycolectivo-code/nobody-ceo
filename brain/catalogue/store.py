"""Acceso a los dominios de catálogo (albums, tracks) en NOBODY_BRAIN."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class Album:
    id: str
    title: str
    source_path: str
    genre_tag: str | None = None
    release_date: str | None = None
    artwork_path: str | None = None


@dataclass
class Track:
    id: str
    album_id: str
    title: str
    audio_path: str
    duration_seconds: float | None = None
    format: str | None = None


def upsert_album(conn: sqlite3.Connection, album: Album) -> None:
    conn.execute(
        """
        INSERT INTO albums (id, title, source_path, genre_tag, release_date, artwork_path)
        VALUES (:id, :title, :source_path, :genre_tag, :release_date, :artwork_path)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            source_path = excluded.source_path,
            genre_tag = excluded.genre_tag,
            release_date = excluded.release_date,
            artwork_path = excluded.artwork_path
        """,
        asdict(album),
    )


def upsert_track(conn: sqlite3.Connection, track: Track) -> None:
    conn.execute(
        """
        INSERT INTO tracks (id, album_id, title, audio_path, duration_seconds, format)
        VALUES (:id, :album_id, :title, :audio_path, :duration_seconds, :format)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            audio_path = excluded.audio_path,
            duration_seconds = excluded.duration_seconds,
            format = excluded.format
        """,
        asdict(track),
    )


def list_albums(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM albums ORDER BY title").fetchall()


def list_tracks(conn: sqlite3.Connection, album_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tracks WHERE album_id = ? ORDER BY title", (album_id,)
    ).fetchall()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    albums = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    return {"albums": albums, "tracks": tracks}
