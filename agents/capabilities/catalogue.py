"""Ingesta de solo lectura del catálogo de NØBØĐ¥ hacia NOBODY_BRAIN.

Nunca escribe, mueve, renombra ni elimina nada bajo la ruta del catálogo —
solo lee metadata (vía ffprobe, que no decodifica el archivo completo) y
escribe en la base propia del proyecto (data/nobody.db).

Uso:
    python -m agents.capabilities.catalogue --root "D:\\Users\\Santiago\\Desktop\\NOBODY"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from brain.catalogue.store import Album, Track, upsert_album, upsert_track
from brain.db import connect

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}

# Heurística por palabras clave en el nombre del álbum — no es dato verificado.
# El pipeline anterior (ya perdido) usaba una idea similar; se reconstruye
# aquí desde cero, sin reutilizar su código.
GENRE_KEYWORDS = {
    "FLAMENCO": ["flamenco", "gipsy", "tango"],
    "ANDINO": ["andin", "altiplano", "inca", "pachamama", "andes", "sol del"],
    "PSICODELICO": ["psicodel", "psychedelic", "trance", "acido", "ácido"],
    "FRECUENCIAS": ["hz", "frequenc", "528", "healing", "sanacion", "sanación"],
    "CUMBIA": ["cumbia"],
    "RITUAL": ["ritual", "ceremonia", "sagrad", "esfera de luz"],
}


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "sin-nombre"


def guess_genre(album_name: str) -> str | None:
    lowered = album_name.lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return genre
    return None


def probe_duration(path: Path) -> float | None:
    """Duración vía ffprobe. No decodifica el archivo — solo lee su cabecera."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


@dataclass
class AlbumScan:
    name: str
    path: Path
    audio_files: list[Path] = field(default_factory=list)
    image_files: list[Path] = field(default_factory=list)
    video_files: list[Path] = field(default_factory=list)
    other_files: list[Path] = field(default_factory=list)


def scan_album(album_path: Path) -> AlbumScan:
    scan = AlbumScan(name=album_path.name, path=album_path)
    for p in album_path.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            scan.audio_files.append(p)
        elif ext in IMAGE_EXTENSIONS:
            scan.image_files.append(p)
        elif ext in VIDEO_EXTENSIONS:
            scan.video_files.append(p)
        else:
            scan.other_files.append(p)
    return scan


def pick_artwork(scan: AlbumScan) -> Path | None:
    """Solo considera imágenes en la raíz del álbum (no en subcarpetas de
    producción como CANVAS_*), y solo si hay una candidata inequívoca."""
    root_images = [p for p in scan.image_files if p.parent == scan.path]
    return root_images[0] if len(root_images) == 1 else None


def ingest(catalogue_root: Path, dry_run: bool = False) -> dict:
    conn = connect()

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalogue_root": str(catalogue_root),
        "dry_run": dry_run,
        "albums": [],
        "loose_root_files": [],
        "totals": {"albums": 0, "tracks": 0, "audio_bytes": 0},
    }

    for entry in sorted(catalogue_root.iterdir()):
        if entry.is_file():
            report["loose_root_files"].append(entry.name)
            continue
        if not entry.is_dir():
            continue

        scan = scan_album(entry)
        album_id = slugify(scan.name)
        artwork = pick_artwork(scan)

        album = Album(
            id=album_id,
            title=scan.name,
            source_path=str(entry),
            genre_tag=guess_genre(scan.name),
            artwork_path=str(artwork) if artwork else None,
        )

        tracks: list[Track] = []
        audio_bytes = 0
        for audio_path in scan.audio_files:
            rel = audio_path.relative_to(entry).with_suffix("")
            track_id = f"{album_id}/{slugify(str(rel))}"
            size = audio_path.stat().st_size
            audio_bytes += size
            tracks.append(
                Track(
                    id=track_id,
                    album_id=album_id,
                    title=audio_path.stem,
                    audio_path=str(audio_path),
                    duration_seconds=probe_duration(audio_path),
                    format=audio_path.suffix.lstrip(".").lower(),
                )
            )

        if not dry_run:
            upsert_album(conn, album)
            for t in tracks:
                upsert_track(conn, t)
            conn.commit()

        report["albums"].append(
            {
                "id": album_id,
                "title": scan.name,
                "genre_tag_guess": album.genre_tag,
                "artwork_found": bool(artwork),
                "artwork_ambiguous": len(scan.image_files) > 1 and artwork is None,
                "track_count": len(tracks),
                "tracks_missing_duration": sum(
                    1 for t in tracks if t.duration_seconds is None
                ),
                "image_files": len(scan.image_files),
                "video_files": len(scan.video_files),
                "other_files": len(scan.other_files),
                "audio_bytes": audio_bytes,
            }
        )
        report["totals"]["albums"] += 1
        report["totals"]["tracks"] += len(tracks)
        report["totals"]["audio_bytes"] += audio_bytes

    conn.close()
    return report


def render_markdown(report: dict) -> str:
    t = report["totals"]
    lines = [
        "# CATALOGUE_REPORT",
        "",
        f"Generado: {report['generated_at']}",
        f"Raíz escaneada (solo lectura): `{report['catalogue_root']}`",
        f"Modo: {'dry-run (no escribió en NOBODY_BRAIN)' if report['dry_run'] else 'escrito en NOBODY_BRAIN'}",
        "",
        f"**{t['albums']} álbumes · {t['tracks']} tracks · {t['audio_bytes'] / 1e9:.2f} GB de audio**",
        "",
        "## Álbumes",
        "",
        "| Álbum | Género (heurística) | Tracks | Sin duración | Portada | Video/otros |",
        "|---|---|---:|---:|---|---:|",
    ]
    for a in report["albums"]:
        portada = "sí" if a["artwork_found"] else ("ambigua" if a["artwork_ambiguous"] else "no")
        lines.append(
            f"| {a['title']} | {a['genre_tag_guess'] or '—'} | {a['track_count']} | "
            f"{a['tracks_missing_duration']} | {portada} | "
            f"{a['video_files']} video / {a['other_files']} otros |"
        )
    if report["loose_root_files"]:
        lines += ["", "## Archivos sueltos en la raíz (no asignados a ningún álbum)", ""]
        lines += [f"- {name}" for name in report["loose_root_files"]]
    lines += [
        "",
        "## Notas de método",
        "",
        "- El género es una heurística por palabras clave en el nombre del álbum "
        "— no es dato verificado, revisar antes de usarlo en una decisión.",
        "- Subcarpetas que replican los mismos títulos en otro formato (p. ej. `wav/`) "
        "se indexan como tracks separados, mismo título con `format` distinto — no se "
        "dedujo automáticamente cuál versión es la maestra.",
        "- Archivos dentro de subcarpetas de producción (`CANVAS_*`) y video de stock "
        "suelto (`pexels_*`) se cuentan como video/otros pero no se ingieren como "
        "tracks — son activos de producción, no catálogo musical.",
        "- Los archivos sueltos en la raíz del catálogo (fuera de una carpeta de álbum) "
        "no se asignan a ningún álbum — se listan aparte para que nada quede oculto.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de solo lectura del catálogo NØBØĐ¥")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="No escribe en NOBODY_BRAIN, solo genera el reporte",
    )
    parser.add_argument("--out", type=Path, default=Path("CATALOGUE_REPORT.md"))
    args = parser.parse_args()

    if not args.root.exists():
        raise SystemExit(f"No existe la ruta del catálogo: {args.root}")

    report = ingest(args.root, dry_run=args.dry_run)
    args.out.write_text(render_markdown(report), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Reporte escrito en {args.out} "
        f"({report['totals']['albums']} álbumes, {report['totals']['tracks']} tracks)"
    )


if __name__ == "__main__":
    main()
