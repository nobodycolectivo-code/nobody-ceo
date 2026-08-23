"""Cliente de solo lectura para YouTube Data API v3 + YouTube Analytics API.

No sube, no borra, no modifica nada — únicamente GET. Construido sobre
credenciales reutilizadas del pipeline anterior (ver .env y la nota de
decisión ahí); no se asume qué scopes fueron otorgados originalmente,
se verifican en tiempo de ejecución con granted_scopes().
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SUBSCRIBERS_TARGET = 1000
WATCH_HOURS_TARGET = 4000


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


def granted_scopes() -> list[str]:
    """Qué puede leer realmente este token — se verifica contra Google,
    no se asume, porque el token es reutilizado de otro proyecto."""
    creds = _credentials()
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"access_token": creds.token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("scope", "").split()


@dataclass
class ChannelSnapshot:
    channel_id: str
    title: str
    subscriber_count: int
    view_count: int
    video_count: int
    hidden_subscriber_count: bool


def get_channel_snapshot() -> ChannelSnapshot:
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("La cuenta autenticada no tiene ningún canal de YouTube.")
    item = items[0]
    stats = item["statistics"]
    return ChannelSnapshot(
        channel_id=item["id"],
        title=item["snippet"]["title"],
        subscriber_count=int(stats.get("subscriberCount", 0)),
        view_count=int(stats.get("viewCount", 0)),
        video_count=int(stats.get("videoCount", 0)),
        hidden_subscriber_count=bool(stats.get("hiddenSubscriberCount", False)),
    )


def get_watch_hours(days: int = 365) -> float:
    """Horas de vista estimadas en los últimos `days` días, vía YouTube
    Analytics API. Requiere el scope yt-analytics.readonly — si el token
    reutilizado no lo tiene, lanza PermissionError con un mensaje claro
    en vez de un traceback críptico de Google."""
    creds = _credentials()
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    end = date.today()
    start = end - timedelta(days=days)
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="estimatedMinutesWatched",
            )
            .execute()
        )
    except HttpError as e:
        if e.resp.status in (401, 403):
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "") if e.error_details else ""
            except Exception:
                reason = ""
            if reason == "accessNotConfigured" or "has not been used in project" in str(e):
                raise PermissionError(
                    "La YouTube Analytics API no está habilitada en el "
                    "proyecto de Google Cloud de este cliente OAuth — hay "
                    "que habilitarla en console.cloud.google.com (Library "
                    "→ YouTube Analytics API → Enable) y esperar unos "
                    "minutos. No es un problema de scope."
                ) from e
            raise PermissionError(
                "El token de YouTube no tiene el scope yt-analytics.readonly "
                "— no se pueden leer horas de vista. Hay que re-consentir el "
                "acceso con ese scope incluido."
            ) from e
        raise
    rows = resp.get("rows") or [[0]]
    minutes = rows[0][0]
    return minutes / 60


def get_video_stats(video_id: str) -> dict:
    """Vistas/likes/comentarios de un video puntual, vía Data API."""
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.videos().list(part="statistics", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return {}
    stats = items[0]["statistics"]
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


def get_video_watch_hours(video_id: str, days: int = 365) -> float | None:
    """Horas de vista de un video puntual, vía Analytics API. Los datos de
    Analytics tienen 24-48h de rezago — un video recién publicado da 0
    aunque ya tenga vistas reales (esas sí aparecen en get_video_stats).
    None si Analytics falla (scope/API no habilitada)."""
    creds = _credentials()
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    end = date.today()
    start = end - timedelta(days=days)
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="estimatedMinutesWatched",
                filters=f"video=={video_id}",
            )
            .execute()
        )
    except HttpError:
        return None
    rows = resp.get("rows") or [[0]]
    return rows[0][0] / 60


def objective_001_progress() -> dict:
    """Snapshot directo contra el Objetivo 001 (desbloquear watch page
    ads): suscriptores y horas de vista calificadas vs. 1,000 / 4,000."""
    snapshot = get_channel_snapshot()
    try:
        watch_hours = get_watch_hours(days=365)
        watch_hours_error = None
    except PermissionError as e:
        watch_hours = None
        watch_hours_error = str(e)

    return {
        "channel_title": snapshot.title,
        "subscribers": snapshot.subscriber_count,
        "subscribers_target": SUBSCRIBERS_TARGET,
        "subscribers_gap": max(0, SUBSCRIBERS_TARGET - snapshot.subscriber_count),
        "watch_hours_365d": watch_hours,
        "watch_hours_target": WATCH_HOURS_TARGET,
        "watch_hours_gap": (
            max(0, WATCH_HOURS_TARGET - watch_hours)
            if watch_hours is not None
            else None
        ),
        "watch_hours_error": watch_hours_error,
    }


if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

    load_dotenv()
    print("Scopes otorgados a este token:", granted_scopes())
    print(json.dumps(objective_001_progress(), indent=2, ensure_ascii=False))
