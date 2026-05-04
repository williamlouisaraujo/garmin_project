from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import pandas as pd

from src.db import get_supabase


def get_accounts() -> list[dict]:
    """Retourne la liste des comptes Garmin configurés."""
    db = get_supabase()
    response = db.table("settings").select("value").eq("key", "garmin_accounts").execute()
    if response.data:
        try:
            return json.loads(response.data[0]["value"])
        except (json.JSONDecodeError, KeyError):
            pass

    # Rétrocompatibilité : compte unique stocké avec les anciennes clés
    email = get_setting("garmin_email")
    password = get_setting("garmin_password")
    if email and password:
        return [{"email": email, "password": password, "label": email}]
    return []


def save_accounts(accounts: list[dict]) -> None:
    db = get_supabase()
    db.table("settings").upsert(
        {"key": "garmin_accounts", "value": json.dumps(accounts)},
        on_conflict="key",
    ).execute()


def save_activities(raw_list: list[dict], garmin_account: str = "") -> int:
    """
    Insère ou met à jour les activités Garmin pour un compte donné.
    Retourne le nombre de nouvelles activités détectées.
    """
    from src.transform import normalize_activity

    db = get_supabase()

    normalized_rows = []
    seen_ids = set()
    for raw in raw_list:
        row = normalize_activity(raw)
        if row is None:
            continue
        activity_id = row["activity_id"]
        if activity_id in seen_ids:
            continue
        seen_ids.add(activity_id)
        row["garmin_account"] = garmin_account
        normalized_rows.append(row)

    if normalized_rows:
        candidate_ids = [row["activity_id"] for row in normalized_rows]
        existing = db.table("activities").select("activity_id").in_("activity_id", candidate_ids).execute()
        existing_ids = {row["activity_id"] for row in (existing.data or [])}
        new_rows = [row for row in normalized_rows if row["activity_id"] not in existing_ids]
    else:
        new_rows = []

    if new_rows:
        db.table("activities").upsert(
            new_rows,
            on_conflict="activity_id",
            ignore_duplicates=True,
        ).execute()
    new_count = len(new_rows)

    db.table("sync_log").insert({
        "synced_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count_new": new_count,
        "garmin_account": garmin_account,
    }).execute()

    return new_count


def get_activities_df(garmin_account: Optional[str] = None) -> pd.DataFrame:
    db = get_supabase()
    query = db.table("activities").select("*").order("start_time", desc=True)

    if garmin_account:
        query = query.eq("garmin_account", garmin_account)

    response = query.execute()

    if not response.data:
        return pd.DataFrame()

    df = pd.DataFrame(response.data)

    if "garmin_account" not in df.columns:
        df["garmin_account"] = ""

    return df


def get_last_sync(garmin_account: Optional[str] = None) -> str:
    db = get_supabase()
    query = db.table("sync_log").select("synced_at").order("id", desc=True).limit(1)

    if garmin_account:
        query = query.eq("garmin_account", garmin_account)

    row = query.execute()

    return row.data[0]["synced_at"] if row.data else "Jamais"


def get_setting(key: str) -> Optional[str]:
    db = get_supabase()
    response = db.table("settings").select("value").eq("key", key).execute()

    if response.data:
        return response.data[0]["value"]

    return None


def save_setting(key: str, value: str) -> None:
    db = get_supabase()
    db.table("settings").upsert(
        {"key": key, "value": value},
        on_conflict="key",
    ).execute()


# ── Strava : configuration de l'application (partagée, une seule app) ─────────

def get_strava_app_config() -> Optional[dict]:
    """
    Config partagée de l'app Strava : client_id, client_secret, redirect_uri.
    Une seule config pour toute l'app — tous les comptes utilisateurs passent
    par la même application Strava déclarée sur strava.com/settings/api.
    """
    val = get_setting("strava_app_config")
    if val:
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None

    # Migration depuis l'ancien format strava_credentials (v1, sans multi-compte)
    old = get_setting("strava_credentials")
    if old:
        try:
            d = json.loads(old)
            if d.get("client_id"):
                cfg = {
                    "client_id": d["client_id"],
                    "client_secret": d.get("client_secret", ""),
                    "redirect_uri": d.get("redirect_uri", ""),
                }
                save_strava_app_config(cfg)
                return cfg
        except json.JSONDecodeError:
            pass
    return None


def save_strava_app_config(config: dict) -> None:
    save_setting("strava_app_config", json.dumps({
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": config["redirect_uri"],
    }))


# ── Strava : comptes utilisateurs (un par compte Garmin) ─────────────────────

def get_strava_accounts() -> list[dict]:
    """
    Liste des comptes Strava liés, un par compte Garmin.
    Chaque entrée : {garmin_email, access_token, refresh_token, expires_at, athlete}
    """
    val = get_setting("strava_accounts")
    if not val:
        return []
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return []


def save_strava_accounts(accounts: list[dict]) -> None:
    save_setting("strava_accounts", json.dumps(accounts))


def get_strava_account_for_garmin(garmin_email: str) -> Optional[dict]:
    """Retourne le compte Strava lié à ce compte Garmin, ou None."""
    for acc in get_strava_accounts():
        if acc.get("garmin_email") == garmin_email:
            return acc
    return None


def save_strava_account(strava_account: dict) -> None:
    """Upsert d'un compte Strava identifié par garmin_email."""
    accounts = get_strava_accounts()
    email = strava_account["garmin_email"]
    for i, acc in enumerate(accounts):
        if acc.get("garmin_email") == email:
            accounts[i] = strava_account
            save_strava_accounts(accounts)
            return
    accounts.append(strava_account)
    save_strava_accounts(accounts)


def delete_strava_account(garmin_email: str) -> None:
    """Délie le compte Strava de ce compte Garmin."""
    accounts = [a for a in get_strava_accounts() if a.get("garmin_email") != garmin_email]
    save_strava_accounts(accounts)


# ── Strava : records (depuis vw_strava_records dans Supabase) ─────────────────

_STRAVA_METERS_TO_KM: dict[float, float] = {
    1000.0:    1.0,
    5000.0:    5.0,
    10000.0:  10.0,
    21097.5:  21.0975,
    42195.0:  42.195,
    50000.0:  50.0,
}


def get_strava_records_from_view(garmin_email: str) -> Optional[dict[float, dict]]:
    """
    Retourne les records Strava depuis vw_strava_records (Supabase).
    Résultat : {distance_km (float): {time_s, date, activity_id, activity_name, source}}
    ou None si l'utilisateur n'existe pas ou n'a aucun best_effort synchronisé.
    """
    db = get_supabase()

    user_rows = (
        db.table("user_accounts")
        .select("user_id")
        .eq("garmin_user_id", garmin_email)
        .limit(1)
        .execute()
        .data
    )
    if not user_rows:
        return None
    user_id = user_rows[0]["user_id"]

    rows = (
        db.table("vw_strava_records")
        .select("normalized_distance,best_elapsed_time,activity_id,activity_name,start_date")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    if not rows:
        return None

    result: dict[float, dict] = {}
    for row in rows:
        dist_m = float(row["normalized_distance"])
        dist_km = next(
            (km for m, km in _STRAVA_METERS_TO_KM.items() if abs(m - dist_m) < 1.0),
            None,
        )
        if dist_km is None:
            continue
        t_s = row.get("best_elapsed_time")
        if not t_s:
            continue
        start_date = row.get("start_date") or ""
        try:
            date_str = datetime.fromisoformat(start_date.replace("Z", "")).strftime("%d/%m/%Y")
        except Exception:
            date_str = "—"
        result[dist_km] = {
            "time_s": float(t_s),
            "date": date_str,
            "activity_id": row.get("activity_id"),
            "activity_name": row.get("activity_name") or "—",
            "source": "Strava",
        }

    return result if result else None
