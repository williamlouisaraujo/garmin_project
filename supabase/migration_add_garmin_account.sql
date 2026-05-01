-- Migration : ajout colonne garmin_account pour isoler les données par compte Garmin
-- À exécuter dans : Supabase > SQL Editor > New query

ALTER TABLE activities ADD COLUMN IF NOT EXISTS garmin_account TEXT NOT NULL DEFAULT '';
ALTER TABLE sync_log   ADD COLUMN IF NOT EXISTS garmin_account TEXT NOT NULL DEFAULT '';
