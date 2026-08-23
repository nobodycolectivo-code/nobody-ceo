"""Cliente de solo lectura para Pexels Video API — búsqueda y descarga de
stock de video vertical para el fondo de los reels."""

from __future__ import annotations

import os
from pathlib import Path

import requests

SEARCH_URL = "https://api.pexels.com/videos/search"


def search_vertical_video(query: str, per_page: int = 5) -> list[dict]:
    resp = requests.get(
        SEARCH_URL,
        headers={"Authorization": os.environ["PEXELS_API_KEY"]},
        params={"query": query, "orientation": "portrait", "per_page": per_page, "size": "medium"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def best_vertical_file(video: dict) -> dict | None:
    """De los video_files de un resultado, el más cercano a 1080 de ancho
    entre los que son verticales (alto > ancho)."""
    files = video.get("video_files", [])
    verticals = [f for f in files if (f.get("height") or 0) > (f.get("width") or 0)]
    pool = verticals or files
    if not pool:
        return None
    return min(pool, key=lambda f: abs((f.get("width") or 0) - 1080))


def download_video(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return dest
