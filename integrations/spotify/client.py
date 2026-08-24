"""Cliente de Spotify Web API — creación real de playlists. Requiere una
cuenta con Premium activo (Spotify bloquea buena parte de la API si no,
ver la nota de decisión en .env). Credenciales reutilizadas del motor de
playlists anterior, scopes: playlist-read-private, playlist-modify-
private, playlist-modify-public, ugc-image-upload.
"""

from __future__ import annotations

import base64
import os

import requests

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


def _access_token() -> str:
    auth = base64.b64encode(
        f"{os.environ['SPOTIFY_CLIENT_ID']}:{os.environ['SPOTIFY_CLIENT_SECRET']}".encode()
    ).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "refresh_token", "refresh_token": os.environ["SPOTIFY_REFRESH_TOKEN"]},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_access_token()}"}


def get_current_user_id() -> str:
    resp = requests.get(f"{API_BASE}/me", headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()["id"]


def search_track(query: str) -> dict | None:
    """Primer resultado de track para un query: uri, name, artist. None
    si no hay resultados."""
    resp = requests.get(
        f"{API_BASE}/search",
        headers=_headers(),
        params={"q": query, "type": "track", "limit": 1},
        timeout=20,
    )
    resp.raise_for_status()
    items = resp.json().get("tracks", {}).get("items", [])
    if not items:
        return None
    track = items[0]
    return {
        "uri": track["uri"],
        "name": track["name"],
        "artist": ", ".join(a["name"] for a in track["artists"]),
        "url": track["external_urls"]["spotify"],
    }


def create_playlist(name: str, description: str, public: bool = True) -> str:
    """Crea una playlist para el usuario autenticado. Usa /me/playlists —
    el endpoint viejo /users/{id}/playlists devuelve 403 Forbidden ahora
    (Spotify lo restringió; /me/playlists sigue funcionando)."""
    resp = requests.post(
        f"{API_BASE}/me/playlists",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"name": name, "description": description[:300], "public": public},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def add_tracks(playlist_id: str, track_uris: list[str]) -> None:
    """Spotify devuelve 403 Forbidden en este endpoint para apps en
    Development Mode (confirmado 2026-08-23, no es un bug nuestro —
    'Add Items to Playlist' quedó fuera del acceso estándar; Extended
    Quota Mode exige ser una organización con 250k+ MAU). Se deja la
    función por si Spotify lo desbloquea más adelante — hoy
    agents/capabilities/playlist.py no la llama, entrega la tracklist
    para agregar a mano en su lugar."""
    if not track_uris:
        return
    resp = requests.post(
        f"{API_BASE}/playlists/{playlist_id}/tracks",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"uris": track_uris},
        timeout=20,
    )
    resp.raise_for_status()
