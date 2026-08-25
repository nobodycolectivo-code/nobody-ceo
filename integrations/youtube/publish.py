"""Publicación real en YouTube — única función de este módulo que
escribe en un sistema externo. Usa el mismo cliente OAuth que
integrations.youtube.client, ahora con scope youtube.upload agregado.
"""

from __future__ import annotations

import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
    )
    creds.refresh(Request())
    return creds


def upload_video(
    file_path: str,
    title: str,
    description: str,
    category_id: str = "10",  # Music
    privacy_status: str = "public",
    is_short: bool = False,
    tags: list[str] | None = None,
) -> str:
    """Sube un video/reel real a YouTube. Devuelve el videoId publicado."""
    youtube = build("youtube", "v3", credentials=_credentials())

    final_title = title if not is_short else f"{title} #shorts"
    body = {
        "snippet": {
            "title": final_title[:100],
            "description": description[:5000],
            "categoryId": category_id,
            "tags": tags or ["NOBODY Records", "ambient", "instrumental"],
        },
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def set_thumbnail(video_id: str, thumbnail_path: str) -> None:
    """Sube una miniatura custom para un video ya publicado. Mismo scope
    de OAuth que upload_video (youtube.upload) — no necesita credenciales
    aparte. Quien llama decide si falla la publicación por esto o no."""
    youtube = build("youtube", "v3", credentials=_credentials())
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    ).execute()
