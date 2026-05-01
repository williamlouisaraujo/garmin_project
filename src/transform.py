from __future__ import annotations

from typing import Optional

import pandas as pd


def normalize_activity(raw: dict) -> Optional[dict]:
    """Convertit un dict brut Garmin en ligne normalisée pour SQLite."""
    activity_id = str(raw.get("activityId", "")).strip()
    if not activity_id:
        return None

    distance_m = raw.get("distance") or 0.0
    distance_km = round(float(distance_m) / 1000, 2)

    duration_s = raw.get("duration") or 0.0
    duration_min = round(float(duration_s) / 60, 1)

    pace = None
    if distance_km > 0.1 and duration_min > 0:
        pace = round(duration_min / distance_km, 2)

    activity_type = raw.get("activityType", {})
    if isinstance(activity_type, dict):
        type_key = activity_type.get("typeKey", "unknown")
    else:
        type_key = str(activity_type) if activity_type else "unknown"

    def _int_or_none(val) -> Optional[int]:
        try:
            v = int(float(val))
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    return {
        "activity_id": activity_id,
        "name": raw.get("activityName") or "",
        "type": type_key,
        "start_time": raw.get("startTimeLocal") or "",
        "distance_km": distance_km,
        "duration_min": duration_min,
        "elevation_m": float(raw.get("elevationGain") or 0),
        "avg_hr": _int_or_none(raw.get("averageHR")),
        "max_hr": _int_or_none(raw.get("maxHR")),
        "pace_min_km": pace,
        "calories": _int_or_none(raw.get("calories")),
    }


def format_pace(pace: Optional[float]) -> str:
    if not pace or pace <= 0:
        return "—"
    mins = int(pace)
    secs = int((pace - mins) * 60)
    return f"{mins}:{secs:02d} /km"


def format_duration(duration_min: Optional[float]) -> str:
    if not duration_min or duration_min <= 0:
        return "—"
    h = int(duration_min // 60)
    m = int(duration_min % 60)
    return f"{h}h{m:02d}" if h > 0 else f"{m} min"


def weekly_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["start_time"] = pd.to_datetime(df["start_time"])
    # Lundi de chaque semaine
    df["week"] = (
        df["start_time"] - pd.to_timedelta(df["start_time"].dt.dayofweek, unit="D")
    ).dt.normalize()

    weekly = (
        df.groupby("week")
        .agg(
            distance_km=("distance_km", "sum"),
            elevation_m=("elevation_m", "sum"),
            count=("activity_id", "count"),
        )
        .reset_index()
    )
    weekly["distance_km"] = weekly["distance_km"].round(1)
    weekly["elevation_m"] = weekly["elevation_m"].round(0).astype(int)
    weekly["week_label"] = weekly["week"].dt.strftime("S%V")
    return weekly.sort_values("week").reset_index(drop=True)
