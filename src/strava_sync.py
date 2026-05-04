from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.db import get_supabase
from src.strava_client import STRAVA_API_BASE, get_valid_access_token

import requests


@dataclass
class StravaSyncResult:
    mode: str
    fetched_activities: int = 0
    upserted_activities: int = 0
    detailed_activities: int = 0
    upserted_best_efforts: int = 0
    api_calls: int = 0
    backfill_completed: bool = False
    latest_activity_date_loaded: int | None = None
    oldest_activity_date_loaded: int | None = None
    rate_limit_limit: str = ""
    rate_limit_usage: str = ""


def _utc_epoch(date_str: str | None) -> int | None:
    if not date_str:
        return None
    return int(datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp())


def _api_get(access_token: str, path: str, params: dict[str, Any] | None = None) -> tuple[dict | list | None, dict]:
    resp = requests.get(
        f"{STRAVA_API_BASE}/{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params or {},
        timeout=30,
    )
    headers = {
        "X-RateLimit-Limit": resp.headers.get("X-RateLimit-Limit", ""),
        "X-RateLimit-Usage": resp.headers.get("X-RateLimit-Usage", ""),
    }
    if resp.status_code == 401:
        raise ValueError("Token Strava invalide ou expiré. Reconnectez-vous.")
    if resp.status_code == 429:
        raise RuntimeError("Limite de requêtes Strava atteinte (100/15 min).")
    if not resp.ok:
        return None, headers
    return resp.json(), headers


def _get_or_create_user_id(athlete: dict | None, garmin_email: str | None) -> str:
    db = get_supabase()
    athlete_id = athlete.get("id") if athlete else None

    if athlete_id is not None:
        existing = db.table("user_accounts").select("user_id").eq("strava_athlete_id", athlete_id).limit(1).execute().data
        if existing:
            user_id = existing[0]["user_id"]
            if garmin_email:
                db.table("user_accounts").update({"garmin_user_id": garmin_email}).eq("user_id", user_id).execute()
            return user_id

    if garmin_email:
        existing = db.table("user_accounts").select("user_id").eq("garmin_user_id", garmin_email).limit(1).execute().data
        if existing:
            user_id = existing[0]["user_id"]
            if athlete_id is not None:
                db.table("user_accounts").update({"strava_athlete_id": athlete_id}).eq("user_id", user_id).execute()
            return user_id

    payload = {"strava_athlete_id": athlete_id, "garmin_user_id": garmin_email}
    row = db.table("user_accounts").insert(payload).execute().data
    return row[0]["user_id"]


def run_strava_sync(app_config: dict, strava_account: dict, max_activity_calls: int = 20, max_detail_calls: int = 30) -> StravaSyncResult:
    db = get_supabase()
    athlete = strava_account.get("athlete") or {}
    user_id = _get_or_create_user_id(athlete, strava_account.get("garmin_email"))
    access_token = get_valid_access_token(app_config, strava_account)

    state_rows = db.table("strava_sync_state").select("*").eq("user_id", user_id).limit(1).execute().data
    state = state_rows[0] if state_rows else None

    latest_loaded = state.get("latest_activity_date_loaded") if state else None
    oldest_loaded = state.get("oldest_activity_date_loaded") if state else None
    backfill_completed = bool(state.get("backfill_completed")) if state else False

    mode = "incremental" if latest_loaded else "backfill"
    result = StravaSyncResult(mode=mode)

    activities: list[dict] = []
    before = oldest_loaded

    for _ in range(max_activity_calls):
        params = {"per_page": 200}
        if mode == "backfill" and before:
            params["before"] = before
        if mode == "incremental" and latest_loaded:
            params["after"] = latest_loaded

        batch, headers = _api_get(access_token, "athlete/activities", params)
        result.api_calls += 1
        result.rate_limit_limit = headers.get("X-RateLimit-Limit", "")
        result.rate_limit_usage = headers.get("X-RateLimit-Usage", "")
        if not batch:
            break

        assert isinstance(batch, list)
        activities.extend(batch)

        if mode == "backfill":
            timestamps = [_utc_epoch(a.get("start_date")) for a in batch]
            timestamps = [t for t in timestamps if t is not None]
            if not timestamps:
                break
            before = min(timestamps) - 1
            if len(batch) < 200:
                break
        else:
            if len(batch) < 200:
                break

    result.fetched_activities = len(activities)

    if activities:
        rows = []
        for a in activities:
            rows.append({
                "activity_id": a["id"],
                "user_id": user_id,
                "name": a.get("name"),
                "type": a.get("type"),
                "distance_m": a.get("distance"),
                "moving_time_s": a.get("moving_time"),
                "elapsed_time_s": a.get("elapsed_time"),
                "total_elevation_gain_m": a.get("total_elevation_gain"),
                "start_date": a.get("start_date"),
                "start_date_local": a.get("start_date_local"),
                "timezone": a.get("timezone"),
                "raw_json": a,
            })
        db.table("strava_activities").upsert(rows, on_conflict="activity_id").execute()
        result.upserted_activities = len(rows)

        ts = sorted([_utc_epoch(a.get("start_date")) for a in activities if _utc_epoch(a.get("start_date"))])
        if ts:
            min_ts, max_ts = ts[0], ts[-1]
            newest = max(latest_loaded or 0, max_ts)
            oldest = min(oldest_loaded or min_ts, min_ts)
            result.latest_activity_date_loaded = newest
            result.oldest_activity_date_loaded = oldest
            if mode == "backfill" and len(activities) < (max_activity_calls * 200):
                backfill_completed = True
    else:
        result.latest_activity_date_loaded = latest_loaded
        result.oldest_activity_date_loaded = oldest_loaded

    # Detail sync: prioritise current batch, then backfill any historical gaps
    run_ids_batch = [a["id"] for a in activities if a.get("type") in ("Run", "TrailRun")]
    if run_ids_batch:
        already_in_batch = {
            r["activity_id"]
            for r in (
                db.table("strava_activity_details")
                .select("activity_id")
                .in_("activity_id", run_ids_batch)
                .execute()
                .data or []
            )
        }
        to_detail = [aid for aid in run_ids_batch if aid not in already_in_batch]
    else:
        to_detail = []

    # Fill remaining budget with historical run activities that have no detail yet
    remaining = max_detail_calls - len(to_detail)
    if remaining > 0:
        all_run_ids = {
            r["activity_id"]
            for r in (
                db.table("strava_activities")
                .select("activity_id")
                .eq("user_id", user_id)
                .in_("type", ["Run", "TrailRun"])
                .limit(5000)
                .execute()
                .data or []
            )
        }
        all_detailed_ids = {
            r["activity_id"]
            for r in (
                db.table("strava_activity_details")
                .select("activity_id")
                .eq("user_id", user_id)
                .limit(5000)
                .execute()
                .data or []
            )
        }
        batch_set = set(run_ids_batch)
        missing_history = sorted(
            (aid for aid in all_run_ids if aid not in all_detailed_ids and aid not in batch_set),
            reverse=True,  # plus récent en premier
        )
        to_detail.extend(missing_history[:remaining])

    to_detail = to_detail[:max_detail_calls]

    for aid in to_detail:
        detail, headers = _api_get(access_token, f"activities/{aid}")
        result.api_calls += 1
        result.rate_limit_limit = headers.get("X-RateLimit-Limit", "")
        result.rate_limit_usage = headers.get("X-RateLimit-Usage", "")
        if not detail:
            continue
        db.table("strava_activity_details").upsert({"activity_id": aid, "user_id": user_id, "raw_json": detail}, on_conflict="activity_id").execute()
        result.detailed_activities += 1

        best_rows = []
        for be in detail.get("best_efforts") or []:
            best_rows.append({
                "activity_id": aid,
                "user_id": user_id,
                "name": be.get("name"),
                "distance": be.get("distance"),
                "elapsed_time": be.get("elapsed_time"),
                "start_index": be.get("start_index"),
                "end_index": be.get("end_index"),
                "pr_rank": be.get("pr_rank"),
                "start_date_local": be.get("start_date_local"),
                "raw_json": be,
            })
        if best_rows:
            db.table("strava_best_efforts").upsert(
                best_rows,
                on_conflict="activity_id,name,distance,start_index,end_index",
            ).execute()
            result.upserted_best_efforts += len(best_rows)

    db.table("strava_sync_state").upsert({
        "user_id": user_id,
        "latest_activity_date_loaded": result.latest_activity_date_loaded,
        "oldest_activity_date_loaded": result.oldest_activity_date_loaded,
        "backfill_completed": backfill_completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="user_id").execute()

    result.backfill_completed = backfill_completed
    return result
