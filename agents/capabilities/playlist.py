"""El CEO como curador de playlists de Spotify.

Spotify bloquea "Add Items to Playlist" para apps en Development Mode
(confirmado en vivo, 2026-08-23 y reverificado 2026-08-25 con una
playlist de prueba real — 403 Forbidden, no es un bug de acá ni un tema
de scopes; Extended Quota Mode exige ser una organización con 250k+
usuarios activos mensuales). Por eso el CEO NO crea la playlist vacía
por API — eso deja un cascarón sin canciones dando vueltas en Spotify,
peor que no hacer nada (decisión de Santiago, 2026-08-25). El flujo real
es:

1. El CEO diseña nombre, descripción y tracklist (públicos reales +
   propios de NØBØĐ¥ intercalados cada 3-4 canciones).
2. Entrega todo listo para pegar — Santiago (o quien tenga la app de
   Spotify a mano) crea la playlist y agrega las canciones a mano.

Si Spotify habilita Extended Quota Mode más adelante, integrations.
spotify.client.add_tracks ya está implementado — solo falta volver a
llamar create_playlist()/add_tracks() acá.
"""

from __future__ import annotations

import json
import os
import uuid

import anthropic

from brain.content.store import ContentItem, already_used_source_ids, insert
from brain.db import connect
from brain.decisions.store import Decision, record as record_decision
from integrations.spotify.client import search_track

CLAUDE_MODEL = "claude-sonnet-5"
PUBLIC_TRACKS_PER_NOBODY_TRACK = 3  # 1 track propio cada 3 públicos
PLAYLIST_SIZE = 24


def _playlist_brief(genre_tag: str, sample_albums: list[str]) -> dict:
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=(
                "Eres el curador de playlists de NØBØĐ¥ Records en Spotify. "
                "Para un género/mood dado, diseñas una playlist pública real "
                "con canciones de otros artistas que encajen en ese mood — no "
                "una playlist genérica, algo con identidad propia.\n\n"
                "Responde ÚNICAMENTE JSON crudo, sin bloque de código markdown "
                "(nada de ```), sin texto antes ni después:\n"
                '{"name": "nombre de la playlist, máximo 60 caracteres", '
                '"description": "máximo 20 palabras, una sola frase", '
                '"track_queries": ["query 1", "..."]}\n'
                "track_queries debe tener EXACTAMENTE 8 elementos, cada uno "
                "corto (máximo 5 palabras): 'canción artista' o un mood buscable "
                "en Spotify. Sé breve en todo — esto se corta si es muy largo."
            ),
            messages=[{"role": "user", "content": (
                f"Género/mood: {genre_tag}. Álbumes propios en ese estilo: "
                f"{', '.join(sample_albums)}."
            )}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.startswith("json") else text
        brief = json.loads(text.strip())
        if not brief.get("track_queries"):
            raise ValueError("brief sin track_queries")
        return brief
    except Exception:
        return {
            "name": f"NØBØĐ¥ presenta: {genre_tag.title()}",
            "description": f"Una selección {genre_tag.lower()} curada por NØBØĐ¥ Records.",
            "track_queries": [genre_tag] * 8,
        }


def pick_next_playlist_genre(conn) -> tuple[str, list[str]] | None:
    used = already_used_source_ids(conn, "playlist")
    rows = conn.execute(
        "SELECT genre_tag, title FROM albums WHERE genre_tag IS NOT NULL"
    ).fetchall()
    by_genre: dict[str, list[str]] = {}
    for r in rows:
        by_genre.setdefault(r["genre_tag"], []).append(r["title"])
    for genre, albums in by_genre.items():
        if genre not in used:
            return genre, albums[:5]
    return None


def _build_tracklist(brief: dict, sample_albums: list[str]) -> list[dict]:
    """Intercala tracks públicos (búsqueda real) con tracks propios cada
    PUBLIC_TRACKS_PER_NOBODY_TRACK canciones. Cada entrada trae
    is_nobody para que el mensaje final los distinga."""
    tracklist: list[dict] = []
    seen_uris: set[str] = set()
    album_cycle = list(sample_albums)
    album_idx = 0
    query_idx = 0
    public_since_last_nobody = 0

    while len(tracklist) < PLAYLIST_SIZE and (
        query_idx < len(brief["track_queries"]) * 3
    ):
        if (
            public_since_last_nobody >= PUBLIC_TRACKS_PER_NOBODY_TRACK
            and album_cycle
        ):
            album_title = album_cycle[album_idx % len(album_cycle)]
            album_idx += 1
            try:
                track = search_track(f"{album_title} NOBODY Records")
            except Exception:
                track = None
            # La búsqueda de Spotify es texto libre — puede devolver un
            # track de OTRO artista que solo coincide por palabras (pasó
            # en pruebas: "Ashtar Being", "Nobody Serious"). Solo se
            # marca is_nobody si el artista devuelto realmente contiene
            # "nobody" — si no, es que ese track propio no está (todavía)
            # distribuido/indexado en Spotify, y se omite sin inventar.
            if (
                track
                and track["uri"] not in seen_uris
                and "nobody" in track["artist"].lower()
            ):
                seen_uris.add(track["uri"])
                tracklist.append({**track, "is_nobody": True})
                public_since_last_nobody = 0
                continue
            public_since_last_nobody = 0

        query = brief["track_queries"][query_idx % len(brief["track_queries"])]
        query_idx += 1
        try:
            track = search_track(query)
        except Exception:
            track = None
        if track and track["uri"] not in seen_uris:
            seen_uris.add(track["uri"])
            tracklist.append({**track, "is_nobody": False})
            public_since_last_nobody += 1

    return tracklist


def format_tracklist_message(item_title: str, description: str, tracklist: list[dict]) -> str:
    lines = [
        f"Playlist curada: '{item_title}'",
        description,
        "",
        "Creála en Spotify y pegá estos tracks en orden:",
    ]
    for i, t in enumerate(tracklist, 1):
        tag = " ← NØBØĐ¥" if t["is_nobody"] else ""
        lines.append(f"{i}. {t['name']} — {t['artist']}{tag}")
        lines.append(f"   {t['url']}")
    nobody_count = sum(1 for t in tracklist if t["is_nobody"])
    lines.append(f"\n{len(tracklist)} tracks, {nobody_count} propios de NØBØĐ¥.")
    return "\n".join(lines)


def generate_playlist() -> tuple[ContentItem, str] | None:
    """Devuelve (ContentItem, mensaje_con_tracklist) o None si no hay
    géneros nuevos para curar. No crea nada en Spotify — 'Add Items to
    Playlist' está bloqueado por Development Mode (ver docstring del
    módulo), así que una playlist vacía es peor que ninguna. El
    ContentItem queda status='draft': curado, pendiente de que alguien
    lo cree a mano."""
    conn = connect()
    picked = pick_next_playlist_genre(conn)
    if picked is None:
        conn.close()
        return None
    genre_tag, sample_albums = picked

    brief = _playlist_brief(genre_tag, sample_albums)
    tracklist = _build_tracklist(brief, sample_albums)

    item_id = f"playlist-{genre_tag.lower()}-{uuid.uuid4().hex[:6]}"
    item = ContentItem(
        id=item_id, kind="playlist", source_type="genre", source_id=genre_tag,
        title=brief["name"],
        description=brief["description"] + " [pendiente de crear y cargar a mano en Spotify]",
        status="draft",
    )
    insert(conn, item)
    nobody_count = sum(1 for t in tracklist if t["is_nobody"])
    record_decision(
        conn,
        Decision(
            objective_id=None,
            evidence=f"genero={genre_tag}, tracks={len(tracklist)}, propios={nobody_count}",
            reasoning=(
                f"[curador playlist] queries={brief['track_queries']}. "
                "No se crea en Spotify — add_tracks sigue bloqueado (403, "
                "Development Mode), una playlist vacía es peor que ninguna."
            ),
            action=f"Playlist curada (pendiente de crear a mano): '{brief['name']}'",
            expected_result="Santiago crea la playlist y pega la tracklist entregada",
        ),
    )
    conn.commit()
    conn.close()

    message = format_tracklist_message(item.title, brief["description"], tracklist)
    return item, message


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    result = generate_playlist()
    if result is None:
        print("No hay géneros nuevos para armar playlist.")
    else:
        item, message = result
        print(item.status)
        print(message)
