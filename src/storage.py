import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "garmin.db"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id   TEXT PRIMARY KEY,
                name          TEXT,
                type          TEXT,
                start_time    TEXT,
                distance_km   REAL,
                duration_min  REAL,
                elevation_m   REAL,
                avg_hr        INTEGER,
                max_hr        INTEGER,
                pace_min_km   REAL,
                calories      INTEGER
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at   TEXT NOT NULL,
                count_new   INTEGER NOT NULL DEFAULT 0
            )
        """)


def save_activities(raw_list: list[dict]) -> int:
    """Insert new activities, skip duplicates. Returns count of inserted rows."""
    from src.transform import normalize_activity

    init_db()
    count_new = 0

    with _conn() as con:
        for raw in raw_list:
            row = normalize_activity(raw)
            if row is None:
                continue
            exists = con.execute(
                "SELECT 1 FROM activities WHERE activity_id = ?", (row["activity_id"],)
            ).fetchone()
            if exists:
                continue
            con.execute(
                """INSERT INTO activities
                   (activity_id, name, type, start_time, distance_km, duration_min,
                    elevation_m, avg_hr, max_hr, pace_min_km, calories)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["activity_id"], row["name"], row["type"], row["start_time"],
                    row["distance_km"], row["duration_min"], row["elevation_m"],
                    row["avg_hr"], row["max_hr"], row["pace_min_km"], row["calories"],
                ),
            )
            count_new += 1

        con.execute(
            "INSERT INTO sync_log (synced_at, count_new) VALUES (?, ?)",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), count_new),
        )

    return count_new


def get_activities_df() -> pd.DataFrame:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM activities ORDER BY start_time DESC"
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def get_sync_summary() -> dict:
    init_db()
    with _conn() as con:
        last_row = con.execute(
            "SELECT synced_at FROM sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        count_row = con.execute("SELECT COUNT(*) FROM activities").fetchone()

    last_sync = last_row[0] if last_row else "Jamais"
    total_activities = count_row[0] if count_row else 0

    df = get_activities_df()
    if df.empty:
        return {
            "last_sync": last_sync,
            "total_activities": total_activities,
            "total_distance_km": 0.0,
            "total_elevation_m": 0,
            "total_duration_h": 0.0,
        }

    return {
        "last_sync": last_sync,
        "total_activities": total_activities,
        "total_distance_km": round(df["distance_km"].sum(), 1),
        "total_elevation_m": int(df["elevation_m"].sum()),
        "total_duration_h": round(df["duration_min"].sum() / 60, 1),
    }
