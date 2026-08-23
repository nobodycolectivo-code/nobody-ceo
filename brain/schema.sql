-- NOBODY_BRAIN v0.1 — esquema propuesto (SQLite)
--
-- Una sola base de datos (data/nobody.db, fuera de git) respaldando los seis
-- dominios de brain/. Este archivo es la propuesta de modelo de datos para
-- revisión — no se ha ejecutado contra ninguna base todavía.

PRAGMA foreign_keys = ON;

-- ── Catalogue ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS albums (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    source_path   TEXT NOT NULL,   -- ruta original en el catálogo (solo lectura)
    genre_tag     TEXT,
    release_date  TEXT,
    artwork_path  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracks (
    id             TEXT PRIMARY KEY,
    album_id       TEXT NOT NULL REFERENCES albums(id),
    title          TEXT NOT NULL,
    audio_path     TEXT,
    duration_seconds REAL,
    format         TEXT,
    platform_ids   TEXT,           -- JSON: {"youtube": "...", "spotify": "...", "distrokid": "..."}
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Metrics ──────────────────────────────────────────────────────────────
-- Serie temporal genérica: una fila por (plataforma, asset, fecha, métrica).
CREATE TABLE IF NOT EXISTS metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT NOT NULL,     -- youtube | spotify | distrokid
    asset_id     TEXT,              -- track_id / album_id / NULL para métricas de canal
    metric_date  TEXT NOT NULL,     -- ISO date
    metric_name  TEXT NOT NULL,     -- views, watch_time_hours, subscribers, streams, saves, revenue_usd...
    metric_value REAL NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, asset_id, metric_date, metric_name)
);

-- ── Objectives ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS objectives (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    baseline_json TEXT NOT NULL,    -- snapshot JSON al crear el objetivo
    target_json   TEXT NOT NULL,
    deadline      TEXT,
    status        TEXT NOT NULL DEFAULT 'active',  -- active | achieved | abandoned
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Decisions ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT REFERENCES objectives(id),
    decided_at      TEXT NOT NULL DEFAULT (datetime('now')),
    evidence        TEXT,            -- qué datos se usaron
    reasoning       TEXT,            -- razonamiento resumido
    action          TEXT NOT NULL,   -- qué se decidió
    expected_result TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'  -- pending | executed | superseded
);

-- ── Experiments ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS experiments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis    TEXT NOT NULL,
    asset_id      TEXT,
    channel       TEXT,
    started_at    TEXT NOT NULL DEFAULT (datetime('now')),
    target_metric TEXT,
    result        TEXT,
    learning      TEXT,
    status        TEXT NOT NULL DEFAULT 'running'  -- running | done | abandoned
);

-- ── Learnings ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learnings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    summary              TEXT NOT NULL,
    source_experiment_id INTEGER REFERENCES experiments(id),
    confidence           TEXT,        -- low | medium | high
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Expenses / Royalties ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date   TEXT NOT NULL,
    entry_type   TEXT NOT NULL,       -- revenue | expense
    source       TEXT NOT NULL,       -- distrokid | spotify | youtube | manual
    amount_usd   REAL NOT NULL,
    note         TEXT,
    approved_by  TEXT,                -- obligatorio para entry_type = 'expense' (ver GOVERNANCE.md)
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Content (reels / videos generados y publicados) ───────────────────────
CREATE TABLE IF NOT EXISTS content_items (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,       -- reel | long_video
    source_type    TEXT NOT NULL,       -- track | album
    source_id      TEXT NOT NULL,       -- track_id o album_id
    render_path    TEXT,
    title          TEXT,
    description    TEXT,
    status         TEXT NOT NULL DEFAULT 'draft',  -- draft | rendered | published | failed
    platform       TEXT,                -- youtube
    platform_video_id TEXT,
    error          TEXT,
    objective_id   TEXT REFERENCES objectives(id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    published_at   TEXT
);
