"""Capability: sincroniza métricas de plataformas externas hacia NOBODY_BRAIN.

Solo lectura contra las plataformas — únicamente escribe en la base
propia del proyecto.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from brain.db import connect
from brain.metrics.store import Metric, record_metric
from brain.objectives.store import Objective, seed_if_missing
from integrations.youtube.client import objective_001_progress

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


if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(sync_youtube_metrics(), indent=2, ensure_ascii=False))
