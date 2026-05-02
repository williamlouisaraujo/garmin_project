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