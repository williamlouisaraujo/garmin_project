from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from src.db import get_supabase


def save_activities(raw_list: list[dict]) -> int:
    """Insère les nouvelles activités, ignore les doublons. Retourne le nombre d'insérées."""
    from src.transform import normalize_activity

    db = get_supabase()

    existing = db.table("activities").select("activity_id").execute()
    existing_ids = {row["activity_id"] for row in existing.data}

    new_rows = []
    for raw in raw_list:
        row = normalize_activity(raw)
        if row is None or row["activity_id"] in existing_ids:
            continue
        new_rows.append(row)

    if new_rows:
        db.table("activities").insert(new_rows).execute()

    db.table("sync_log").insert({
        "synced_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count_new": len(new_rows),
    }).execute()

    return len(new_rows)


def get_activities_df() -> pd.DataFrame:
    db = get_supabase()
    response = db.table("activities").select("*").order("start_time", desc=True).execute()
    if not response.data:
        return pd.DataFrame()
    return pd.DataFrame(response.data)


def get_sync_summary() -> dict:
    db = get_supabase()

    last_row = (
        db.table("sync_log").select("synced_at").order("id", desc=True).limit(1).execute()
    )
    last_sync = last_row.data[0]["synced_at"] if last_row.data else "Jamais"

    df = get_activities_df()
    if df.empty:
        return {
            "last_sync": last_sync,
            "total_activities": 0,
            "total_distance_km": 0.0,
            "total_elevation_m": 0,
            "total_duration_h": 0.0,
        }

    return {
        "last_sync": last_sync,
        "total_activities": len(df),
        "total_distance_km": round(df["distance_km"].sum(), 1),
        "total_elevation_m": int(df["elevation_m"].sum()),
        "total_duration_h": round(df["duration_min"].sum() / 60, 1),
    }


def get_setting(key: str) -> Optional[str]:
    db = get_supabase()
    response = db.table("settings").select("value").eq("key", key).execute()
    if response.data:
        return response.data[0]["value"]
    return None


def save_setting(key: str, value: str) -> None:
    db = get_supabase()
    db.table("settings").upsert({"key": key, "value": value}).execute()
