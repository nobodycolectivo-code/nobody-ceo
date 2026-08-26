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
# Deliberadamente NO vive en /data (el volumen de 500MB ya está justo con
# la base, los renders pendientes y el cache de stock) — queda en el
# filesystem efímero del contenedor, que se limpia solo en cada restart.
# Pero un video largo puede descargar 8 tracks .wav sin comprimir de un
# álbum (150-400MB fácil) y ESE filesystem también tiene cupo limitado —
# visto en producción, 2026-08-26: "Conversion failed!" al final de un
# render de 23 minutos, con toda la pinta de quedarse sin espacio justo
# al escribir el archivo final. Sin tope, esto crece sin límite dentro
# de la vida del contenedor.
CATALOGUE_CACHE_MAX_BYTES = 400_000_000


def _prune_catalogue_cache(max_bytes: int = CATALOGUE_CACHE_MAX_BYTES) -> None:
    if not CATALOGUE_CACHE_DIR.exists():
        return
    files = [f for f in CATALOGUE_CACHE_DIR.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    if total <= max_bytes:
        return
    files.sort(key=lambda f: f.stat().st_atime)  # más antiguo (por uso) primero
    for f in files:
        if total <= max_bytes:
            break
        size = f.stat().st_size
        try:
            f.unlink()
            total -= size
        except OSError:
            continue


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

    _prune_catalogue_cache()

    from integrations.r2.client import download_file

    download_file(relative_path, cached)
    return str(cached)
