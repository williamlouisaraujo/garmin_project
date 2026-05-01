from __future__ import annotations

from typing import Optional

import pandas as pd


def normalize_activity(raw: dict) -> Optional[dict]:
    """Convertit un dict brut Garmin en ligne normalisée pour Supabase."""
    activity_id = str(raw.get("activityId", "")).strip()
    if not activity_id:
        return None

    distance_m = raw.get("distance") or 0.0
    distance_km = round(float(distance_m) / 1000, 2)

    duration_s = raw.get("duration") or 0.0
    duration_min = round(float(duration_s) / 60, 4)

    pace = None
    if distance_km > 0.1 and duration_min > 0:
        pace = round(duration_min / distance_km, 4)

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
    secs = int(round((pace - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d} /km"


def format_duration(duration_min: Optional[float]) -> str:
    if not duration_min or duration_min <= 0:
        return "—"
    total_s = int(round(duration_min * 60))
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def format_duration_hms(total_seconds: int) -> str:
    """Format seconds as h:mm:ss or mm:ss."""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def compute_vap(
    pace_min_km: Optional[float],
    elevation_m: Optional[float],
    distance_km: Optional[float],
) -> Optional[float]:
    """Approximation de la VAP (allure ajustée à la pente) pour une activité entière."""
    if not pace_min_km or pace_min_km <= 0:
        return None
    if not distance_km or distance_km < 0.1 or not elevation_m or elevation_m <= 0:
        return pace_min_km
    grade_pct = (elevation_m / (distance_km * 1000)) * 100
    if grade_pct >= 0:
        factor = 1 + 0.033 * grade_pct
    else:
        factor = max(0.88, 1 + 0.020 * grade_pct)
    return round(pace_min_km / factor, 4) if factor > 0 else pace_min_km


def weekly_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["start_time"] = pd.to_datetime(df["start_time"])
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

    # Remplir les semaines sans activité
    if not weekly.empty:
        all_weeks = pd.date_range(
            start=weekly["week"].min(),
            end=weekly["week"].max(),
            freq="W-MON",
        )
        full = pd.DataFrame({"week": all_weeks})
        weekly = full.merge(weekly, on="week", how="left")
        weekly["distance_km"] = weekly["distance_km"].fillna(0.0)
        weekly["elevation_m"] = weekly["elevation_m"].fillna(0).astype(int)
        weekly["count"] = weekly["count"].fillna(0).astype(int)

    weekly["week_end"] = weekly["week"] + pd.Timedelta(days=6)
    weekly["week_label"] = (
        "S"
        + weekly["week"].dt.strftime("%V")
        + "  "
        + weekly["week"].dt.strftime("%d/%m")
        + " → "
        + weekly["week_end"].dt.strftime("%d/%m")
    )

    return weekly.sort_values("week").reset_index(drop=True)
