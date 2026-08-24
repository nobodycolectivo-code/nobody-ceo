"""Búsqueda de videos de otros canales + publicación real de comentarios.

Requiere el scope youtube.force-ssl (agregado a get_refresh_token.py) —
sin él, insert_comment falla con 403/401, igual que pasó con upload
antes de tener el scope correcto.
"""

from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


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


def search_videos(query: str, max_results: int = 10) -> list[dict]:
    """Videos públicos de OTROS canales (no el nuestro) para un query dado."""
    youtube = build("youtube", "v3", credentials=_credentials())
    resp = youtube.search().list(
        part="snippet", q=query, type="video", order="relevance",
        maxResults=max_results, relevanceLanguage="es",
    ).execute()
    return [
        {
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "channel_title": item["snippet"]["channelTitle"],
            "channel_id": item["snippet"]["channelId"],
            "description": item["snippet"].get("description", ""),
        }
        for item in resp.get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def post_comment(video_id: str, text: str) -> str:
    """Publica un comentario real de nivel superior en un video. Devuelve
    el commentId."""
    youtube = build("youtube", "v3", credentials=_credentials())
    resp = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        },
    ).execute()
    return resp["id"]
