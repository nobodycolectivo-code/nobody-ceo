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

-- ── Royalties (import de exports de DistroKid) ────────────────────────────
-- Capa inmutable: una fila por línea de CSV vista, en cualquier export
-- importado. La idempotencia viene de row_hash = sha256 del contenido
-- íntegro de la fila fuente (las 15 columnas originales del export),
-- NUNCA de las columnas dimensionales — DistroKid re-reporta meses ya
-- reportados con cifras corregidas (restatements) en exports posteriores,
-- así que una clave dimensional (mes+store+isrc+país) no es estable en
-- el tiempo y puede aparecer legítimamente más de una vez el mismo día
-- (líneas adicionales aditivas, no duplicados). Ver docs de la auditoría.
CREATE TABLE IF NOT EXISTS royalty_facts_raw (
    row_hash        TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    source_row_num  INTEGER NOT NULL,
    imported_at     TEXT NOT NULL DEFAULT (datetime('now')),

    date_inserted   TEXT NOT NULL,
    reporting_date  TEXT NOT NULL,
    sale_month      TEXT NOT NULL,
    store           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    title           TEXT NOT NULL,
    isrc            TEXT,
    upc             TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    team_percentage REAL NOT NULL,
    source_type     TEXT NOT NULL,
    country_of_sale TEXT NOT NULL,
    songwriter_withheld_usd REAL NOT NULL,
    earnings_usd    REAL NOT NULL,
    recoup_usd      REAL
);

CREATE INDEX IF NOT EXISTS idx_royalty_raw_dims
    ON royalty_facts_raw (sale_month, store, isrc, upc, country_of_sale, reporting_date);

-- Vista resuelta: para cada combinación (mes de venta, store, isrc, upc,
-- país) toma únicamente las filas del reporting_date MÁS RECIENTE visto
-- para esa combinación (así una restatement posterior reemplaza, no se
-- suma, a la cifra anterior) y suma entre sí las filas que comparten ese
-- mismo reporting_date (líneas aditivas legítimas del mismo export).
-- Todo el motor de inteligencia consulta esta vista, nunca la tabla raw.
CREATE VIEW IF NOT EXISTS royalty_facts_resolved AS
WITH latest_reporting AS (
    SELECT sale_month, store, isrc, upc, country_of_sale,
           MAX(reporting_date) AS reporting_date
    FROM royalty_facts_raw
    GROUP BY sale_month, store, isrc, upc, country_of_sale
)
SELECT
    r.sale_month,
    r.store,
    r.isrc,
    r.upc,
    r.country_of_sale,
    r.reporting_date,
    r.title,
    r.source_type,
    SUM(r.quantity) AS quantity,
    SUM(r.earnings_usd) AS earnings_usd,
    SUM(r.songwriter_withheld_usd) AS songwriter_withheld_usd
FROM royalty_facts_raw r
JOIN latest_reporting lr
    ON r.sale_month = lr.sale_month
   AND r.store = lr.store
   AND r.isrc IS lr.isrc
   AND r.upc = lr.upc
   AND r.country_of_sale = lr.country_of_sale
   AND r.reporting_date = lr.reporting_date
GROUP BY r.sale_month, r.store, r.isrc, r.upc, r.country_of_sale,
         r.reporting_date, r.title, r.source_type;

-- Vínculo (opcional, explícito) entre un ISRC del export y un track local
-- del catálogo. track_id queda NULL cuando no hay match suficientemente
-- confiable — nunca se fuerza ni se inventa el vínculo.
CREATE TABLE IF NOT EXISTS royalty_track_links (
    isrc             TEXT PRIMARY KEY,
    upc              TEXT NOT NULL,
    title            TEXT NOT NULL,
    track_id         TEXT REFERENCES tracks(id),
    album_id         TEXT REFERENCES albums(id),
    match_method     TEXT NOT NULL,   -- exact_title | fuzzy_title | unmatched
    match_confidence REAL NOT NULL,   -- 0.0–1.0
    linked_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Snapshot versionado del Hero Engine — se apila en cada corrida, nunca
-- se sobreescribe, para poder ver cómo cambió la clasificación de un
-- track en el tiempo.
CREATE TABLE IF NOT EXISTS hero_classifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at         TEXT NOT NULL DEFAULT (datetime('now')),
    isrc                TEXT NOT NULL,
    track_id            TEXT REFERENCES tracks(id),
    title               TEXT NOT NULL,
    classification      TEXT NOT NULL,  -- HERO | RISING | EVERGREEN | DORMANT | DECLINING | EXPERIMENT
    hero_score          REAL NOT NULL,
    confidence          REAL NOT NULL,
    reason_codes        TEXT NOT NULL,  -- JSON array de strings
    supporting_metrics  TEXT NOT NULL   -- JSON object
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
    -- draft | rendered | pending_review | published | rejected | failed
    -- pending_review: solo reels (decisión 2026-08-26) — renderizado,
    -- esperando aprobación por Telegram antes de subir a YouTube.
    status         TEXT NOT NULL DEFAULT 'draft',
    platform       TEXT,                -- youtube
    platform_video_id TEXT,
    error          TEXT,
    objective_id   TEXT REFERENCES objectives(id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    published_at   TEXT
);

-- ── Creative memory (Fase 1 del Creative QA, 2026-08-26) ──────────────────
-- Estructura lo que antes solo vivía como texto libre en Decision.reasoning
-- — sin esto "no repetición" y "aprendizaje" no tienen dónde pararse. Ver
-- la auditoría del sprint para el razonamiento completo.
CREATE TABLE IF NOT EXISTS creative_briefs (
    content_item_id  TEXT PRIMARY KEY REFERENCES content_items(id),
    hook             TEXT,
    body             TEXT,             -- micro-intención del acto central (2026-08-26)
    mood             TEXT,
    cta              TEXT,             -- generado por pieza, nunca "suscríbete" (2026-08-26)
    structure_json   TEXT NOT NULL,   -- clip_queries, segment_dur, etc. — JSON
    source           TEXT NOT NULL,   -- claude | fallback
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Registro de assets de stock usados por pieza — la deduplicación real
-- entre piezas (Fase 2) se construye sobre esto; acá solo se registra.
CREATE TABLE IF NOT EXISTS used_assets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id  TEXT NOT NULL REFERENCES content_items(id),
    asset_type       TEXT NOT NULL,   -- pexels_video
    asset_ref        TEXT NOT NULL,   -- id del video en Pexels
    used_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
