-- ============================================================
-- Garmin Dashboard — Schéma Supabase
-- À coller et exécuter dans : Supabase > SQL Editor > New query
-- ============================================================

-- Activités Garmin
CREATE TABLE IF NOT EXISTS activities (
    activity_id     TEXT PRIMARY KEY,
    name            TEXT,
    type            TEXT,
    start_time      TEXT,
    distance_km     FLOAT,
    duration_min    FLOAT,
    elevation_m     FLOAT,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    pace_min_km     FLOAT,
    calories        INTEGER,
    garmin_account  TEXT NOT NULL DEFAULT ''
);

-- Log des synchronisations
CREATE TABLE IF NOT EXISTS sync_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    synced_at       TEXT NOT NULL,
    count_new       INTEGER NOT NULL DEFAULT 0,
    garmin_account  TEXT NOT NULL DEFAULT ''
);

-- Paramètres de l'application (credentials Garmin, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Désactiver RLS (app personnelle, accès protégé par APP_PASSWORD côté Streamlit)
ALTER TABLE activities DISABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log   DISABLE ROW LEVEL SECURITY;
ALTER TABLE settings   DISABLE ROW LEVEL SECURITY;
