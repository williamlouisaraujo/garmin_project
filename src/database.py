import os
from datetime import datetime

from supabase import Client, create_client


def get_supabase_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def get_latest_sync_summary() -> dict:
    return {
        "last_sync": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "weekly_km": 42.3,
        "weekly_elevation": 610,
        "sleep_hours": 7.1,
        "hrv": 61,
        "fatigue": "Modérée",
    }