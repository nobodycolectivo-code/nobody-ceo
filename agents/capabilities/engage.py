"""Comenta en videos de OTROS canales dentro de nuestro nicho — no es
publicación propia, es engagement real para ganar visibilidad orgánica.

Autonomía total (decisión de Santiago, 2026-08-23), pero con salvaguardas
de diseño para no caer en el patrón que YouTube marca como spam:
- Nunca menciona el propio canal, no pide suscribirse, no pone links —
  la visibilidad viene de que el nombre del comentarista ya es
  clickeable, no de un CTA dentro del texto.
- Un comentario genuino y específico por video (vía Claude), nunca una
  plantilla repetida.
- Tope diario bajo (COMMENTS_PER_CICLO) — nada de comentar en masa.
- Nunca repite video ya comentado (reutiliza content_items con
  kind='comment' para el chequeo de duplicados, igual que reels/videos).
"""

from __future__ import annotations

import os
import uuid

import anthropic

from brain.content.store import ContentItem, already_used_source_ids, insert
from brain.db import connect
from brain.decisions.store import Decision, record as record_decision
from integrations.youtube.comment import post_comment, search_videos

CLAUDE_MODEL = "claude-sonnet-5"
COMMENTS_PER_CICLO = 10

ENGAGE_QUERIES = [
    "ambient music mix",
    "andean flute meditation music",
    "psychedelic cumbia",
    "528 hz healing frequency",
    "focus music instrumental",
]


def _comment_text(video: dict) -> str | None:
    """Comentario genuino sobre ESE video específico. None si Claude
    falla — nunca se inventa un texto genérico de relleno."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=150,
            system=(
                "Eres un oyente real de música ambient/instrumental comentando "
                "en YouTube. Escribes un comentario corto (1-2 frases), genuino "
                "y específico sobre ESE video — no genérico, no aplicable a "
                "cualquier video. En el mismo idioma del título.\n\n"
                "NUNCA menciones tu propio canal, nunca pidas suscribirse, "
                "nunca pongas un link — eso es spam y hace que YouTube penalice "
                "la cuenta que comenta. Responde SOLO el texto del comentario, "
                "nada más, sin comillas."
            ),
            messages=[{"role": "user", "content": (
                f"Título del video: {video['title']}\n"
                f"Canal: {video['channel_title']}\n"
                f"Descripción: {video['description'][:300]}"
            )}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None
    except Exception:
        return None


def run_engagement_cycle(max_comments: int = COMMENTS_PER_CICLO) -> list[dict]:
    conn = connect()
    used = already_used_source_ids(conn, "comment")
    results: list[dict] = []

    for query in ENGAGE_QUERIES:
        if len(results) >= max_comments:
            break
        try:
            videos = search_videos(query, max_results=5)
        except Exception:
            continue
        for video in videos:
            if len(results) >= max_comments:
                break
            if video["video_id"] in used:
                continue

            text = _comment_text(video)
            if not text:
                continue

            item_id = f"comment-{video['video_id']}-{uuid.uuid4().hex[:6]}"
            try:
                comment_id = post_comment(video["video_id"], text)
                status, error = "published", None
            except Exception as e:
                comment_id, status, error = None, "failed", str(e)[:2000]

            item = ContentItem(
                id=item_id, kind="comment", source_type="youtube_video",
                source_id=video["video_id"], title=video["title"][:200],
                description=text, status=status,
                platform="youtube" if comment_id else None,
                platform_video_id=comment_id, error=error,
            )
            insert(conn, item)
            record_decision(
                conn,
                Decision(
                    objective_id=None,
                    evidence=f"video={video['video_id']} canal='{video['channel_title']}' query='{query}'",
                    reasoning="Engagement genuino en nicho propio, sin auto-promoción en el texto.",
                    action=f"Comentario en '{video['title'][:80]}': {text}",
                    expected_result="Visibilidad orgánica vía el perfil del comentarista",
                    status="executed" if status == "published" else "failed",
                ),
            )
            conn.commit()
            used.add(video["video_id"])
            results.append(
                {
                    "video_id": video["video_id"],
                    "channel": video["channel_title"],
                    "status": status,
                    "comment": text,
                }
            )

    conn.close()
    return results


if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(run_engagement_cycle(), indent=2, ensure_ascii=False))
