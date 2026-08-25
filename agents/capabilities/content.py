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

from agents.capabilities.catalogue_cache import resolve_catalogue_file
from brain.content.store import ContentItem, already_used_source_ids, insert, mark_rendered
from brain.db import connect
from brain.decisions.store import Decision, record as record_decision
from integrations.pexels.client import (
    best_horizontal_file,
    best_vertical_file,
    download_video,
    search_horizontal_video,
    search_vertical_video,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FONT_PATH = REPO_ROOT / "assets" / "fonts" / "Inter-Regular.ttf"

RENDER_DIR = Path(os.environ.get("NOBODY_RENDER_DIR", "render_output"))
STOCK_CACHE_DIR = RENDER_DIR / "stock_cache"
REEL_DURATION = 45  # segundos, formato short/reel
CLAUDE_MODEL = "claude-sonnet-5"

FALLBACK_BG_COLOR = "0x1b1d1c"  # coherente con el neutro del resto del proyecto
CTA_TEXT = "SUSCRÍBETE — NØBØĐ¥ RECORDS"

GENRE_TO_STOCK_QUERY = {
    "ANDINO": "andes mountains nature",
    "PSICODELICO": "psychedelic abstract colors",
    "FRECUENCIAS": "meditation sound healing",
    "CUMBIA": "tropical colorful dance",
    "FLAMENCO": "flamenco fire dance",
    "RITUAL": "ritual candles ceremony",
}
DEFAULT_STOCK_QUERY = "ambient nature calm"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "sin-nombre"


def _summarize_ffmpeg_error(stderr: str, limit: int = 3000) -> str:
    """Guarda la parte útil del stderr en vez de solo la cola — la línea
    de configuración de build de ffmpeg (--enable-x --enable-y...) puede
    ocupar 1000+ caracteres ella sola y desplazar la sección real
    (análisis de inputs, mapping, primer error) fuera de la ventana. Si
    aparece "Input #0" se arranca ahí; si no, desde el principio."""
    if len(stderr) <= limit:
        return stderr
    half = limit // 2
    start = stderr.find("Input #0")
    head_start = start if start != -1 else 0
    return f"{stderr[head_start:head_start + half]}\n...[recortado]...\n{stderr[-half:]}"


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


def _creative_brief(track_row, album_row) -> dict:
    """El CEO actuando como curador: para ESTA canción específica —no una
    fórmula fija por género— decide un hook de apertura y varias
    búsquedas de video distintas entre sí. Si Claude falla, cae a un
    brief determinístico de una sola búsqueda por género (nunca bloquea
    la generación), pero el camino normal es una decisión nueva cada vez."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=(
                "Eres el curador creativo de NØBØĐ¥ Records. Para cada canción "
                "diseñas un reel corto pensado para retener atención y volverse "
                "viral: un hook de apertura y una selección de video de stock "
                "que capture el mood específico de ESA canción, no una fórmula "
                "genérica de género. Evita repetir la misma idea visual entre "
                "las búsquedas — cada una debe aportar una imagen distinta. "
                "Prefiere escenas luminosas y con movimiento visible (nada de "
                "fondos negros o casi estáticos) — el video es el fondo de un "
                "reel vertical y tiene que sostener la atención.\n\n"
                "Responde ÚNICAMENTE el JSON crudo, sin bloque de código markdown "
                "(nada de ```), sin texto antes ni después. Estructura EXACTA, "
                "sin excederla:\n"
                '{"hook": "máximo 6 palabras en español, sin punto final", '
                '"clip_queries": ["query 1", "query 2", "query 3"], '
                '"mood": "una palabra"}\n'
                "clip_queries debe tener EXACTAMENTE 3 elementos, cada uno una "
                "búsqueda corta en inglés (máximo 5 palabras)."
            ),
            messages=[{"role": "user", "content": (
                f"Canción: {track_row['title']}. Álbum: {album_row['title']}. "
                f"Género/mood conocido: {album_row['genre_tag'] or 'ambient instrumental'}."
            )}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.startswith("json") else text
        brief = json.loads(text.strip())
        if not brief.get("clip_queries"):
            raise ValueError("brief sin clip_queries")
        brief["source"] = "claude"
        return brief
    except Exception:
        fallback_query = GENRE_TO_STOCK_QUERY.get(album_row["genre_tag"], DEFAULT_STOCK_QUERY)
        return {
            "hook": track_row["title"],
            "clip_queries": [fallback_query],
            "mood": album_row["genre_tag"] or "ambient",
            "source": "fallback",
        }


MIN_CLIP_BRIGHTNESS = 40  # 0-255; por debajo de esto, el clip se ve casi negro


def _average_brightness(video_path: Path, at_seconds: float = 2.0) -> float | None:
    """Brillo promedio de un frame de muestra (escala de grises, 0-255).
    None si no se pudo leer el archivo."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video_path),
                "-frames:v", "1", "-vf", "scale=32:32", "-pix_fmt", "gray",
                "-f", "rawvideo", "-",
            ],
            capture_output=True, timeout=20,
        )
        data = result.stdout
        return sum(data) / len(data) if data else None
    except Exception:
        return None


def _get_stock_clips(track_row, queries: list[str], max_clips: int = 4) -> list[Path]:
    """Descarga (o reutiliza de cache) un clip vertical por cada query del
    brief creativo — cacheado por track, porque el brief es por canción,
    no por álbum. Prueba hasta 3 resultados por query y descarta los que
    salen casi negros (pasa en la práctica con clips tipo 'cymatics' o
    de fondo oscuro) antes de conformarse con uno."""
    clips: list[Path] = []
    safe_id = track_row["id"].replace("/", "-")
    for i, query in enumerate(queries[:max_clips]):
        cache_path = STOCK_CACHE_DIR / f"{safe_id}-{i}.mp4"
        if cache_path.exists():
            clips.append(cache_path)
            continue
        try:
            videos = search_vertical_video(query, per_page=3)
        except Exception:
            continue
        chosen = None
        for video in videos:
            file = best_vertical_file(video)
            if not file or not file.get("link"):
                continue
            try:
                candidate = download_video(file["link"], cache_path.with_suffix(".tmp.mp4"))
            except Exception:
                continue
            # brightness=None significa que ffmpeg no pudo decodificar ni
            # un frame de prueba — casi siempre un download corrupto o
            # incompleto. Aceptarlo "por las dudas" (como hacía antes)
            # metía ese clip roto al concat final, donde el encoder se
            # quedaba trabado en frame=0 sin nunca fallar limpio — visto
            # en producción. Un probe que falla se descarta, no se acepta.
            if candidate.stat().st_size == 0:
                candidate.unlink(missing_ok=True)
                continue
            brightness = _average_brightness(candidate)
            if brightness is not None and brightness >= MIN_CLIP_BRIGHTNESS:
                candidate.replace(cache_path)
                chosen = cache_path
                break
            candidate.unlink(missing_ok=True)
        if chosen:
            clips.append(chosen)
    return clips


def _get_long_video_background(album_row) -> Path | None:
    """Un clip horizontal de stock para fondo del video largo, cuando el
    álbum no tiene portada — reemplaza la tarjeta negra plana por algo
    con movimiento sutil, con el mismo criterio de género que los reels
    (GENRE_TO_STOCK_QUERY). Cachea por álbum. None si Pexels falla o no
    hay candidato válido — nunca bloquea el render, cae a la tarjeta de
    marca como antes."""
    safe_id = album_row["id"].replace("/", "-")
    cache_path = STOCK_CACHE_DIR / f"longvideo-{safe_id}.mp4"
    if cache_path.exists():
        return cache_path

    query = GENRE_TO_STOCK_QUERY.get(album_row["genre_tag"], DEFAULT_STOCK_QUERY)
    try:
        videos = search_horizontal_video(query, per_page=3)
    except Exception:
        return None

    for video in videos:
        file = best_horizontal_file(video)
        if not file or not file.get("link"):
            continue
        try:
            candidate = download_video(file["link"], cache_path.with_suffix(".tmp.mp4"))
        except Exception:
            continue
        if candidate.stat().st_size == 0:
            candidate.unlink(missing_ok=True)
            continue
        # ver la nota en _get_stock_clips: un probe que no puede
        # decodificar un frame (brightness=None) se descarta, no se
        # acepta — casi siempre es un download corrupto/incompleto.
        brightness = _average_brightness(candidate)
        if brightness is not None and brightness >= MIN_CLIP_BRIGHTNESS:
            candidate.replace(cache_path)
            return cache_path
        candidate.unlink(missing_ok=True)
    return None


def extract_thumbnail(video_path: Path, at_seconds: float | None = None) -> Path | None:
    """Extrae un frame del video ya renderizado como thumbnail — refleja
    lo que el video realmente muestra (portada, stock o tarjeta de marca),
    en vez de generar una imagen aparte que podría no coincidir. None si
    ffmpeg falla (nunca bloquea la publicación por esto)."""
    duration = _ffprobe_duration(video_path) or 60.0
    at_seconds = at_seconds if at_seconds is not None else min(duration * 0.15, 30.0)
    thumb_path = video_path.with_suffix(".thumb.jpg")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video_path),
                "-frames:v", "1", "-q:v", "3", str(thumb_path),
            ],
            capture_output=True, timeout=30,
        )
        return thumb_path if result.returncode == 0 and thumb_path.exists() else None
    except Exception:
        return None


HOOK_WINDOW = 4  # segundos que dura el hook de apertura
CTA_WINDOW = 8  # segundos finales reservados para el CTA


def generate_reel(track_row, album_row) -> ContentItem:
    """Reel vertical 1080x1920 de REEL_DURATION segundos: montaje de varios
    clips de stock elegidos por el CEO como curador para esta canción
    específica (brief vía Claude, ver _creative_brief), hook al abrir,
    CTA al cerrar, waveform del audio real de fondo. `track_row`/
    `album_row` son sqlite3.Row de brain.catalogue.store."""
    item_id = f"reel-{track_row['id'].replace('/', '-')}-{uuid.uuid4().hex[:6]}"
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RENDER_DIR / f"{item_id}.mp4"

    audio_path = resolve_catalogue_file(track_row["audio_path"])
    artwork_path = resolve_catalogue_file(album_row["artwork_path"])
    has_artwork = bool(artwork_path and Path(artwork_path).exists())

    brief = _creative_brief(track_row, album_row)
    clips = _get_stock_clips(track_row, brief["clip_queries"])

    font = _ffmpeg_font_path()
    hook = _escape_drawtext(brief.get("hook") or track_row["title"])
    cta = _escape_drawtext(CTA_TEXT)
    hook_block = (
        f"drawtext=fontfile='{font}':text='{hook}':fontcolor=white:fontsize=52:"
        f"box=1:boxcolor=black@0.45:boxborderw=16:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t\\,0\\,{HOOK_WINDOW})'"
    )
    cta_block = (
        f"drawtext=fontfile='{font}':text='{cta}':fontcolor=white:fontsize=40:"
        f"box=1:boxcolor=black@0.5:boxborderw=18:x=(w-text_w)/2:y=H-280:"
        f"enable='gte(t\\,{REEL_DURATION - CTA_WINDOW})'"
    )

    if clips:
        # Montaje de varios clips distintos — no un solo loop estático.
        segment_dur = REEL_DURATION / len(clips)
        clip_inputs: list[str] = []
        for clip in clips:
            clip_inputs += ["-stream_loop", "-1", "-t", f"{segment_dur:.2f}", "-i", str(clip)]
        # fps=30 normaliza el frame rate de CADA clip de stock antes del
        # concat — un clip con metadata de fps corrupta/absurda (visto en
        # producción: libx264 rechazó el encode por "MB rate > level
        # limit", producido por un frame rate de entrada anómalo que
        # scale/crop no tocan) puede arrastrar esa tasa hasta el encoder
        # final si no se fuerza acá.
        scaled = "".join(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,eq=brightness=-0.1,fps=30[c{i}];"
            for i in range(len(clips))
        )
        concat_labels = "".join(f"[c{i}]" for i in range(len(clips)))
        art_block = (
            f"{scaled}{concat_labels}concat=n={len(clips)}:v=1:a=0,"
            f"{hook_block},{cta_block}[art]"
        )
        bg_input = clip_inputs
        audio_input_index = len(clips)
    elif has_artwork:
        bg_input = ["-loop", "1", "-i", artwork_path]
        art_block = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,boxblur=10:10,eq=brightness=-0.18[bgblur];"
            f"[0:v]scale=980:980[fg];"
            f"[bgblur][fg]overlay=(W-w)/2:(H-h)/2-60,{hook_block},{cta_block}[art]"
        )
        audio_input_index = 1
    else:
        # Sin portada ni stock: tarjeta de marca con el hook.
        bg_input = ["-f", "lavfi", "-i", f"color=c={FALLBACK_BG_COLOR}:s=1080x1920"]
        art_block = f"[0:v]{hook_block},{cta_block}[art]"
        audio_input_index = 1

    filter_complex = (
        f"{art_block};"
        f"[{audio_input_index}:a]showwaves=s=1000x220:mode=cline:colors=white@0.85:rate=25[wave];"
        "[art][wave]overlay=(W-w)/2:H-300[vout]"
    )

    # -threads/-filter_threads acotados: en el contenedor de Railway
    # ffmpeg detecta el CPU count del HOST (visto en logs: threads=60),
    # no el límite real asignado al contenedor — con 3-4 clips
    # decodificándose a la vez más el filtro de concat/overlay, ese
    # sobre-threading agota memoria/CPU y el encoder se queda trabado en
    # frame=0 sin fallar limpio (visto en producción, reproducible con
    # varios clips distintos). Limitarlo explícitamente es la forma
    # estándar de evitar ese problema conocido de ffmpeg en contenedores.
    cmd = [
        "ffmpeg", "-y", "-threads", "2", "-filter_threads", "2",
        *bg_input,
        "-i", audio_path,
        "-t", str(REEL_DURATION),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", f"{audio_input_index}:a",
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", "2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    ok = result.returncode == 0 and out_path.exists()

    meta = _metadata(
        f"Álbum: {album_row['title']}. Canción: {track_row['title']}. "
        f"Mood: {brief.get('mood') or album_row['genre_tag'] or 'ambient instrumental'}. "
        f"Hook usado en el video: {brief.get('hook')}."
    )
    title = meta.get("title") or f"{track_row['title']} — {album_row['title']} | NØBØĐ¥ Records"
    description = meta.get("description") or (
        f"{track_row['title']}, del álbum {album_row['title']}. NØBØĐ¥ Records."
    )

    item = ContentItem(
        id=item_id, kind="reel", source_type="track", source_id=track_row["id"],
        title=title, description=description,
        status="rendered" if ok else "failed",
        error=None if ok else _summarize_ffmpeg_error(result.stderr),
        render_path=str(out_path) if out_path.exists() else None,
    )

    conn = connect()
    insert(conn, item)
    record_decision(
        conn,
        Decision(
            objective_id=None,
            evidence=f"track={track_row['id']}, clips_encontrados={len(clips)}/{len(brief['clip_queries'])}",
            reasoning=(
                f"[curador:{brief.get('source')}] hook='{brief.get('hook')}' "
                f"mood='{brief.get('mood')}' queries={brief['clip_queries']}"
            ),
            action=f"Reel curado para '{track_row['title']}' ({item_id})",
            expected_result="Retener atención (hook) y convertir a suscriptor (CTA de cierre)",
        ),
    )
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

    artwork_path = resolve_catalogue_file(album_row["artwork_path"])
    has_artwork = bool(artwork_path and Path(artwork_path).exists())
    background_clip = None if has_artwork else _get_long_video_background(album_row)
    font = _ffmpeg_font_path()
    album_title = _escape_drawtext(album_row["title"])
    tune_args: list[str] = []

    if has_artwork:
        bg_input = ["-loop", "1", "-i", artwork_path]
        vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
        tune_args = ["-tune", "stillimage"]
    elif background_clip:
        # Stock de fondo en vez de la tarjeta negra plana — mismo criterio
        # de género que los reels (GENRE_TO_STOCK_QUERY). fps=30 normaliza
        # el frame rate del clip (ver generate_reel: un clip con metadata
        # de fps corrupta puede tumbar el encode con "MB rate > level limit").
        bg_input = ["-stream_loop", "-1", "-i", str(background_clip)]
        vf = (
            f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
            f"eq=brightness=-0.25,fps=30,"
            f"drawtext=fontfile='{font}':text='{album_title}':fontcolor=white:"
            f"fontsize=48:box=1:boxcolor=black@0.4:boxborderw=14:"
            f"x=(w-text_w)/2:y=h-110,"
            f"drawtext=fontfile='{font}':text='NØBØĐ¥ Records':fontcolor=white@0.7:"
            f"fontsize=26:x=(w-text_w)/2:y=h-60"
        )
    else:
        bg_input = ["-f", "lavfi", "-i", f"color=c={FALLBACK_BG_COLOR}:s=1280x720"]
        vf = (
            f"drawtext=fontfile='{font}':text='{album_title}':fontcolor=white:"
            f"fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2-30,"
            f"drawtext=fontfile='{font}':text='NØBØĐ¥ Records':fontcolor=white@0.6:"
            f"fontsize=30:x=(w-text_w)/2:y=(h-text_h)/2+50"
        )
        tune_args = ["-tune", "stillimage"]

    audio_inputs = []
    for t in tracks:
        audio_inputs += ["-i", resolve_catalogue_file(t["audio_path"])]
    concat_labels = "".join(f"[{i + 1}:a]" for i in range(len(tracks)))
    filter_complex = f"[0:v]{vf}[bgv];{concat_labels}concat=n={len(tracks)}:v=0:a=1[outa]"

    # ver la nota en generate_reel sobre -threads/-filter_threads: evita
    # que ffmpeg sobre-asigne hilos según el CPU count del host en vez
    # del límite real del contenedor.
    cmd = [
        "ffmpeg", "-y", "-threads", "2", "-filter_threads", "2",
        *bg_input, *audio_inputs,
        "-filter_complex", filter_complex,
        "-map", "[bgv]", "-map", "[outa]",
        "-r", "30",
        "-c:v", "libx264", *tune_args, "-threads", "2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    thumbnail_path = extract_thumbnail(out_path) if result.returncode == 0 and out_path.exists() else None

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
        error=None if result.returncode == 0 else _summarize_ffmpeg_error(result.stderr),
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


def pick_next_reel_source(conn, exclude: frozenset[str] = frozenset()) -> tuple | None:
    """Elige el siguiente track sin reel generado todavía. Orden simple y
    determinístico (por álbum, por título) — no es una heurística de
    performance, solo evita repetir mientras no haya métricas por asset.

    `exclude` es para tracks que ya fallaron EN ESTE MISMO ciclo — un
    reel fallido no cuenta como "usado" (already_used_source_ids solo
    cuenta status != 'failed', a propósito, para poder reintentar en el
    próximo ciclo si fue algo transitorio), pero sin este parámetro el
    loop de reintentos dentro de un mismo ciclo puede quedar atascado
    eligiendo el mismo track que acaba de fallar una y otra vez."""
    used = already_used_source_ids(conn, "reel")
    rows = conn.execute(
        """
        SELECT t.*, a.title AS album_title, a.genre_tag, a.artwork_path
        FROM tracks t JOIN albums a ON a.id = t.album_id
        ORDER BY a.title, t.title
        """
    ).fetchall()
    for row in rows:
        if row["id"] not in used and row["id"] not in exclude:
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
