"""Ciclo autónomo del CEO — OBSERVE → UNDERSTAND → HYPOTHESIZE → DECIDE →
ACT → MEASURE → LEARN, aplicado al Objetivo 001 (unlock YouTube watch
page ads).

Publica de verdad en YouTube. Cada acción queda registrada en
brain/decisions antes y después de ejecutarse, para que sea auditable.

Excepción (decisión de Santiago, 2026-08-26 — revierte parcialmente la
autonomía total de 2026-08-23 documentada en docs/GOVERNANCE.md): los
REELS ya no se publican solos. Quedan en status='pending_review' y
esperan aprobación por Telegram (botones, ver integrations.telegram.
bot) mientras se entrena el criterio del Creative QA (Fase 1: memoria
creativa estructurada, ver brain/creative). Video largo, comentarios y
playlist (curación, no creación en Spotify) siguen autónomos.

Política v1 (simple a propósito, ver docs/CEO_MANDATE.md sobre evitar
abstracción prematura):
  - REELS_POR_CICLO reels por ciclo (uno por track sin usar).
  - 1 video largo por ciclo, del siguiente álbum sin video largo todavía.

Reactivación del canal (decisión de Santiago, 2026-08-23): antes era
1 reel/día y 1 video largo cada 3 días — se sube a 3 reels + 1 video
largo por día.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents.capabilities.content import (
    generate_long_video,
    generate_reel,
    pick_next_long_video_source,
    pick_next_reel_source,
)
from agents.capabilities.engage import run_engagement_cycle
from agents.capabilities.metrics import sync_video_metrics, sync_youtube_metrics
from agents.capabilities.playlist import generate_playlist
from brain.db import connect
from brain.decisions.store import Decision, record as record_decision
from brain.learnings.store import record as record_learning
from integrations.youtube.publish import upload_video

OBJECTIVE_ID = "001-unlock-watch-page-ads"
REELS_POR_CICLO = 3


def publish_item(conn, item, is_short: bool) -> None:
    """Sube `item` a YouTube si está 'rendered'. Compartida con
    integrations.telegram.bot: el flujo normal (video largo) la llama
    directo desde acá; el flujo de reels la llama desde el callback de
    aprobación de Telegram, reconstruyendo un ContentItem desde la fila
    de la base (ver bot._content_item_from_row)."""
    from pathlib import Path

    from brain.content.store import mark_failed, mark_published
    from integrations.youtube.publish import set_thumbnail

    if item.status != "rendered":
        return
    try:
        video_id = upload_video(
            file_path=item.render_path,
            title=item.title,
            description=item.description,
            is_short=is_short,
        )
        mark_published(conn, item.id, video_id)
        conn.commit()

        if item.kind == "long_video":
            # La miniatura es un frame extraído del propio render (ver
            # agents.capabilities.content.extract_thumbnail) — si falla
            # no se falla la publicación, el video ya está arriba.
            thumbnail_path = Path(item.render_path).with_suffix(".thumb.jpg")
            if thumbnail_path.exists():
                try:
                    set_thumbnail(video_id, str(thumbnail_path))
                except Exception:
                    pass

        record_decision(
            conn,
            Decision(
                objective_id=OBJECTIVE_ID,
                evidence=f"content_item={item.id}",
                reasoning="Publicación automática dentro de la política v1 del ciclo diario.",
                action=f"Publicado en YouTube: {item.title} (https://youtu.be/{video_id})",
                expected_result="Contribuir a subscribers y/o watch_hours_365d del Objetivo 001",
            ),
        )
        conn.commit()
    except Exception as e:
        mark_failed(conn, item.id, str(e)[:2000])
        conn.commit()
        record_decision(
            conn,
            Decision(
                objective_id=OBJECTIVE_ID,
                evidence=f"content_item={item.id}",
                reasoning="Intento de publicación falló.",
                action=f"FALLÓ publicar {item.id}: {e}",
                expected_result="N/A",
                status="failed",
            ),
        )
        conn.commit()


def _already_ran_today(conn) -> bool:
    """Evita publicar dos veces el mismo día si el proceso se reinicia
    (crash, redeploy) — el ciclo es de una vez al día, no por arranque."""
    row = conn.execute(
        "SELECT 1 FROM content_items WHERE date(created_at) = date('now') LIMIT 1"
    ).fetchone()
    return row is not None


def run_cycle(force: bool = False) -> dict:
    conn = connect()

    if not force and _already_ran_today(conn):
        conn.close()
        return {"skipped": True, "reason": "ya se generó contenido hoy"}

    # OBSERVE + MEASURE (antes)
    before = sync_youtube_metrics()

    # UNDERSTAND
    objective = conn.execute(
        "SELECT * FROM objectives WHERE id = ?", (OBJECTIVE_ID,)
    ).fetchone()
    target = json.loads(objective["target_json"]) if objective else {}
    subs_gap = max(0, target.get("subscribers", 0) - before["subscribers"])
    hours_gap = (
        max(0, target.get("watch_hours_365d", 0) - before["watch_hours_365d"])
        if before["watch_hours_365d"] is not None
        else None
    )

    actions_taken = []

    # HYPOTHESIZE + DECIDE + ACT: reels (varios por ciclo)
    failed_this_cycle: set[str] = set()
    for _ in range(REELS_POR_CICLO):
        track = pick_next_reel_source(conn, exclude=frozenset(failed_this_cycle))
        if track is None:
            break
        album = conn.execute(
            "SELECT * FROM albums WHERE id = ?", (track["album_id"],)
        ).fetchone()
        reel = generate_reel(track, album)
        record_decision(
            conn,
            Decision(
                objective_id=OBJECTIVE_ID,
                evidence=f"subs_gap={subs_gap}, watch_hours_gap={hours_gap}",
                reasoning=(
                    "Los shorts/reels favorecen descubrimiento y conversión a "
                    "suscriptor más que el watch time puro; se prioriza mientras "
                    "subs_gap > 0."
                ),
                action=f"Generado reel de '{track['title']}' ({album['title']})",
                expected_result="Aportar a subscribers_gap",
            ),
        )
        conn.commit()
        if reel.status == "failed":
            failed_this_cycle.add(track["id"])
        elif reel.status == "rendered":
            # No se publica solo — queda esperando aprobación por Telegram
            # (ver integrations.telegram.bot, decisión 2026-08-26).
            from brain.content.store import mark_pending_review

            mark_pending_review(conn, reel.id)
            conn.commit()
        final = conn.execute(
            "SELECT status, platform_video_id FROM content_items WHERE id = ?", (reel.id,)
        ).fetchone()
        actions_taken.append(
            {"kind": "reel", "id": reel.id, "status": final["status"],
             "video_id": final["platform_video_id"]}
        )

    # HYPOTHESIZE + DECIDE + ACT: video largo (uno por ciclo)
    album, tracks = pick_next_long_video_source(conn)
    if album is not None:
        long_video = generate_long_video(album, tracks)
        record_decision(
            conn,
            Decision(
                objective_id=OBJECTIVE_ID,
                evidence=f"watch_hours_gap={hours_gap}",
                reasoning=(
                    "El video largo es la forma más eficiente de acumular "
                    "watch_hours_365d por unidad de contenido publicado."
                ),
                action=f"Generado video largo del álbum '{album['title']}'",
                expected_result="Aportar a watch_hours_gap",
            ),
        )
        conn.commit()
        publish_item(conn, long_video, is_short=False)
        final = conn.execute(
            "SELECT status, platform_video_id FROM content_items WHERE id = ?",
            (long_video.id,),
        ).fetchone()
        actions_taken.append(
            {"kind": "long_video", "id": long_video.id, "status": final["status"],
             "video_id": final["platform_video_id"]}
        )

    # HYPOTHESIZE + DECIDE + ACT: engagement (comentarios en otros canales)
    for c in run_engagement_cycle():
        actions_taken.append({"kind": "comment", **c})

    # HYPOTHESIZE + DECIDE + ACT: playlist de Spotify (1 por ciclo, por género)
    playlist_message = None
    playlist_result = generate_playlist()
    if playlist_result is not None:
        playlist_item, playlist_message = playlist_result
        actions_taken.append(
            {"kind": "playlist", "id": playlist_item.id, "status": playlist_item.status,
             "video_id": playlist_item.platform_video_id}
        )

    # MEASURE (después)
    after = sync_youtube_metrics()
    sync_video_metrics()

    # LEARN
    record_learning(
        conn,
        summary=(
            f"Ciclo {datetime.now(timezone.utc).date().isoformat()}: "
            f"{len(actions_taken)} acción(es) — {actions_taken}. "
            f"Subs antes/después: {before['subscribers']}/{after['subscribers']}."
        ),
        confidence="low",
    )
    conn.commit()
    conn.close()

    return {
        "before": before, "after": after, "actions": actions_taken,
        "playlist_message": playlist_message,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    result = run_cycle()
    print(json.dumps(result, indent=2, ensure_ascii=False))
