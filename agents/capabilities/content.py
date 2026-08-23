"""Genera reels y videos largos a partir del catálogo real, vía ffmpeg.

Sin TTS ni stock de video de pago en esta versión — portada del álbum
(si existe, si no una tarjeta de color con el nombre) más un overlay de
forma de onda del audio real. Costo marginal: solo una llamada barata a
Claude para título/descripción de YouTube.

No publica nada — eso vive en integrations/youtube/publish.py. Este
módulo solo RENDERIZA archivos locales y los registra en NOBODY_BRAIN.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import anthropic

from brain.content.store import ContentItem, already_used_source_ids, insert, mark_rendered
from brain.db import connect

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FONT_PATH = REPO_ROOT / "assets" / "fonts" / "Inter-Regular.ttf"

RENDER_DIR = Path(os.environ.get("NOBODY_RENDER_DIR", "render_output"))
REEL_DURATION = 45  # segundos, formato short/reel
CLAUDE_MODEL = "claude-sonnet-5"

FALLBACK_BG_COLOR = "0x1b1d1c"  # coherente con el neutro del resto del proyecto


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "sin-nombre"


def _ffmpeg_font_path() -> str:
    """Ruta del font para drawtext, escapada para la sintaxis de filtro de
    ffmpeg. Usa la fuente empaquetada en assets/fonts (Inter, OFL) para que
    funcione igual en Windows local y en el contenedor de Railway — nunca
    depende de una fuente del sistema operativo."""
    path = os.environ.get("NOBODY_FONT_PATH", str(DEFAULT_FONT_PATH))
    return path.replace("\\", "/").replace(":", r"\:")


def _escape_drawtext(text: str) -> str:
    """Escapa un texto para usarlo como valor de text= en drawtext."""
    return (
        text.replace("\\", r"\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
    )


def _metadata(prompt: str) -> dict:
    """Título + descripción cortos vía Claude. Si falla, usa un fallback
    literal (nunca bloquea la generación por esto)."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=(
                "Generas metadata de YouTube para NØBØĐ¥ Records (música ambient/"
                "instrumental con IA). Responde SOLO un JSON con las claves "
                '"title" (menos de 90 caracteres) y "description" (2-3 líneas, '
                "sin hashtags de spam, tono contemplativo). Nada de texto fuera del JSON."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
    except Exception:
        return {}


def _ffprobe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return None


def generate_reel(track_row, album_row) -> ContentItem:
    """Reel vertical 1080x1920 de REEL_DURATION segundos: portada + waveform
    del audio real. `track_row`/`album_row` son sqlite3.Row de brain.catalogue.store."""
    item_id = f"reel-{track_row['id'].replace('/', '-')}-{uuid.uuid4().hex[:6]}"
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RENDER_DIR / f"{item_id}.mp4"

    audio_path = track_row["audio_path"]
    artwork_path = album_row["artwork_path"]
    has_artwork = bool(artwork_path and Path(artwork_path).exists())

    font = _ffmpeg_font_path()
    track_title = _escape_drawtext(track_row["title"])
    album_title = _escape_drawtext(album_row["title"])

    if has_artwork:
        bg_input = ["-loop", "1", "-i", artwork_path]
        art_block = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=10:10,eq=brightness=-0.18[bg];"
            "[0:v]scale=980:980[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2-60[art]"
        )
    else:
        # Sin portada: tarjeta de marca con el título del track/álbum en
        # vez de un video vacío — necesario para que el reel identifique
        # qué es aunque no haya arte disponible para ese álbum.
        bg_input = ["-f", "lavfi", "-i", f"color=c={FALLBACK_BG_COLOR}:s=1080x1920"]
        art_block = (
            f"[0:v]"
            f"drawtext=fontfile='{font}':text='{track_title}':fontcolor=white:"
            f"fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-40,"
            f"drawtext=fontfile='{font}':text='{album_title}':fontcolor=white@0.7:"
            f"fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2+60,"
            f"drawtext=fontfile='{font}':text='NØBØĐ¥ Records':fontcolor=white@0.6:"
            f"fontsize=32:x=(w-text_w)/2:y=140"
            f"[art]"
        )

    filter_complex = (
        f"{art_block};"
        "[1:a]showwaves=s=1000x220:mode=cline:colors=white@0.85:rate=25[wave];"
        "[art][wave]overlay=(W-w)/2:H-300[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *bg_input,
        "-i", audio_path,
        "-t", str(REEL_DURATION),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    meta = _metadata(
        f"Álbum: {album_row['title']}. Canción: {track_row['title']}. "
        f"Género/mood: {album_row['genre_tag'] or 'ambient instrumental'}."
    )
    title = meta.get("title") or f"{track_row['title']} — {album_row['title']} | NØBØĐ¥ Records"
    description = meta.get("description") or (
        f"{track_row['title']}, del álbum {album_row['title']}. NØBØĐ¥ Records."
    )

    item = ContentItem(
        id=item_id, kind="reel", source_type="track", source_id=track_row["id"],
        title=title, description=description,
        status="rendered" if result.returncode == 0 and out_path.exists() else "failed",
        error=None if result.returncode == 0 else result.stderr[-2000:],
        render_path=str(out_path) if out_path.exists() else None,
    )

    conn = connect()
    insert(conn, item)
    conn.commit()
    conn.close()
    return item


def generate_long_video(album_row, track_rows, max_tracks: int = 8) -> ContentItem:
    """Video largo 1280x720: varios tracks del álbum concatenados sobre
    una imagen estática (portada o tarjeta de marca). Sin waveform —
    a esta duración (~20-30 min) sería demasiado lento de renderizar,
    y para watch-time una imagen fija es suficiente."""
    tracks = track_rows[:max_tracks]
    item_id = f"long-{album_row['id']}-{uuid.uuid4().hex[:6]}"
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RENDER_DIR / f"{item_id}.mp4"

    artwork_path = album_row["artwork_path"]
    has_artwork = bool(artwork_path and Path(artwork_path).exists())
    font = _ffmpeg_font_path()
    album_title = _escape_drawtext(album_row["title"])

    if has_artwork:
        bg_input = ["-loop", "1", "-i", artwork_path]
        vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    else:
        bg_input = ["-f", "lavfi", "-i", f"color=c={FALLBACK_BG_COLOR}:s=1280x720"]
        vf = (
            f"drawtext=fontfile='{font}':text='{album_title}':fontcolor=white:"
            f"fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2-30,"
            f"drawtext=fontfile='{font}':text='NØBØĐ¥ Records':fontcolor=white@0.6:"
            f"fontsize=30:x=(w-text_w)/2:y=(h-text_h)/2+50"
        )

    audio_inputs = []
    for t in tracks:
        audio_inputs += ["-i", t["audio_path"]]
    concat_labels = "".join(f"[{i + 1}:a]" for i in range(len(tracks)))
    filter_complex = f"[0:v]{vf}[bgv];{concat_labels}concat=n={len(tracks)}:v=0:a=1[outa]"

    cmd = [
        "ffmpeg", "-y",
        *bg_input, *audio_inputs,
        "-filter_complex", filter_complex,
        "-map", "[bgv]", "-map", "[outa]",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    track_list = ", ".join(t["title"] for t in tracks)
    meta = _metadata(
        f"Álbum: {album_row['title']}. Mezcla larga de {len(tracks)} tracks: "
        f"{track_list}. Género/mood: {album_row['genre_tag'] or 'ambient instrumental'}. "
        f"Es un video largo para escuchar de fondo (focus/meditación/trabajo)."
    )
    title = meta.get("title") or f"{album_row['title']} — Full Album | NØBØĐ¥ Records"
    description = meta.get("description") or (
        f"{album_row['title']}: {track_list}. NØBØĐ¥ Records."
    )

    item = ContentItem(
        id=item_id, kind="long_video", source_type="album", source_id=album_row["id"],
        title=title, description=description,
        status="rendered" if result.returncode == 0 and out_path.exists() else "failed",
        error=None if result.returncode == 0 else result.stderr[-2000:],
        render_path=str(out_path) if out_path.exists() else None,
    )

    conn = connect()
    insert(conn, item)
    conn.commit()
    conn.close()
    return item


def pick_next_long_video_source(conn):
    """Elige el siguiente álbum (con al menos 3 tracks) sin video largo
    generado todavía."""
    used = already_used_source_ids(conn, "long_video")
    albums = conn.execute(
        "SELECT * FROM albums ORDER BY title"
    ).fetchall()
    for album in albums:
        if album["id"] in used:
            continue
        tracks = conn.execute(
            "SELECT * FROM tracks WHERE album_id = ? ORDER BY title", (album["id"],)
        ).fetchall()
        if len(tracks) >= 3:
            return album, tracks
    return None, None


def pick_next_reel_source(conn) -> tuple | None:
    """Elige el siguiente track sin reel generado todavía. Orden simple y
    determinístico (por álbum, por título) — no es una heurística de
    performance, solo evita repetir mientras no haya métricas por asset."""
    used = already_used_source_ids(conn, "reel")
    rows = conn.execute(
        """
        SELECT t.*, a.title AS album_title, a.genre_tag, a.artwork_path
        FROM tracks t JOIN albums a ON a.id = t.album_id
        ORDER BY a.title, t.title
        """
    ).fetchall()
    for row in rows:
        if row["id"] not in used:
            return row
    return None


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    conn = connect()
    track = pick_next_reel_source(conn)
    if track is None:
        print("No hay tracks sin reel generado.")
    else:
        album = conn.execute("SELECT * FROM albums WHERE id = ?", (track["album_id"],)).fetchone()
        item = generate_reel(track, album)
        print(item.status, item.render_path or item.error)
