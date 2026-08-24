"""Resuelve una ruta relativa del catálogo (audio_path/artwork_path
guardados en NOBODY_BRAIN) a una ruta local usable por ffmpeg, sin
importar si el proceso corre en la máquina local (con acceso real a
D:\\...\\NOBODY vía NOBODY_CATALOGUE_ROOT) o en Railway (sin ese drive,
descarga bajo demanda desde Cloudflare R2 y cachea en disco — mismo
patrón que ya usa content.py para los clips de stock de Pexels).

Por qué las rutas se guardan relativas en la base: un audio_path absoluto
tipo "D:\\Users\\Santiago\\..." solo tiene sentido en la máquina que hizo
la ingesta — en Railway (Linux, sin esa unidad) esa ruta literalmente no
existe. Guardar la ruta relativa al root del catálogo (agents.capabilities
.catalogue) y resolverla acá según el entorno es lo que hace que el mismo
dato sirva en los dos lugares.
"""

from __future__ import annotations

import os
from pathlib import Path

CATALOGUE_CACHE_DIR = Path(os.environ.get("NOBODY_CATALOGUE_CACHE_DIR", "render_output/catalogue_cache"))


def resolve_catalogue_file(relative_path: str | None) -> str | None:
    """relative_path viene tal como se guardó en la base (separadores '/',
    relativo al root del catálogo). Devuelve una ruta local absoluta lista
    para pasarle a ffmpeg, o None si no había nada que resolver."""
    if not relative_path:
        return None

    cached = CATALOGUE_CACHE_DIR / relative_path
    if cached.exists():
        return str(cached)

    local_root = os.environ.get("NOBODY_CATALOGUE_ROOT")
    if local_root:
        candidate = Path(local_root) / relative_path
        if candidate.exists():
            return str(candidate)

    from integrations.r2.client import download_file

    download_file(relative_path, cached)
    return str(cached)
