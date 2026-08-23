"""Capability: sincroniza métricas de plataformas externas hacia NOBODY_BRAIN.

Solo lectura contra las plataformas — únicamente escribe en la base
propia del proyecto.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from brain.db import connect
from brain.metrics.store import Metric, record_metric
from brain.objectives.store import Objective, seed_if_missing
from integrations.youtube.client import (
    get_video_stats,
    get_video_watch_hours,
    objective_001_progress,
)

OBJECTIVE_001_BASELINE_DATE = "2026-08-17"


def sync_youtube_metrics() -> dict:
    progress = objective_001_progress()
    today = date.today().isoformat()
    conn = connect()

    seed_if_missing(
        conn,
        Objective(
            id="001-unlock-watch-page-ads",
            title="Unlock YouTube Watch Page Ads",
            baseline={
                "date": OBJECTIVE_001_BASELINE_DATE,
                "subscribers": 763,
                "watch_hours_365d": 1860,
            },
            target={"subscribers": 1000, "watch_hours_365d": 4000},
        ),
    )

    record_metric(
        conn,
        Metric(
            platform="youtube",
            metric_date=today,
            metric_name="subscribers",
            metric_value=float(progress["subscribers"]),
        ),
    )
    if progress["watch_hours_365d"] is not None:
        record_metric(
            conn,
            Metric(
                platform="youtube",
                metric_date=today,
                metric_name="watch_hours_365d",
                metric_value=float(progress["watch_hours_365d"]),
            ),
        )
    conn.commit()
    conn.close()

    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "date": today,
        **progress,
    }


def sync_video_metrics() -> dict:
    """Vistas + horas de vista por video publicado — a diferencia de
    sync_youtube_metrics (nivel canal), esto es lo que le permite al CEO
    saber QUÉ reel específico está funcionando, no solo el agregado."""
    conn = connect()
    rows = conn.execute(
        "SELECT id, platform_video_id FROM content_items WHERE platform_video_id IS NOT NULL"
    ).fetchall()
    today = date.today().isoformat()
    synced = 0
    for row in rows:
        video_id = row["platform_video_id"]
        try:
            stats = get_video_stats(video_id)
        except Exception:
            stats = {}
        if stats:
            record_metric(
                conn,
                Metric(
                    platform="youtube", asset_id=row["id"], metric_date=today,
                    metric_name="views", metric_value=float(stats["views"]),
                ),
            )
        watch_hours = get_video_watch_hours(video_id)
        if watch_hours is not None:
            record_metric(
                conn,
                Metric(
                    platform="youtube", asset_id=row["id"], metric_date=today,
                    metric_name="watch_hours", metric_value=watch_hours,
                ),
            )
        synced += 1
    conn.commit()
    conn.close()
    return {"synced_at": datetime.now(timezone.utc).isoformat(), "videos_synced": synced}


if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(sync_youtube_metrics(), indent=2, ensure_ascii=False))
