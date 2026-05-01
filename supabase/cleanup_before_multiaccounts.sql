-- Nettoyage complet des données avant migration multi-comptes
-- À exécuter dans : Supabase > SQL Editor > New query

TRUNCATE TABLE activities RESTART IDENTITY;
TRUNCATE TABLE sync_log   RESTART IDENTITY;

-- Supprime aussi les anciens credentials stockés en clés séparées
-- (remplacés par garmin_accounts en JSON)
DELETE FROM settings WHERE key IN ('garmin_email', 'garmin_password');
