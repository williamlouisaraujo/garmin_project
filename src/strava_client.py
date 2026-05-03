"""
Strava OAuth 2.0 integration and personal record extraction.

Ce qui est disponible via l'API Strava :
- best_efforts par distance standard sur chaque activité détaillée
  Distances : 400m, 1/2 mile, 1k, 1 mile, 2 mile, 5k, 10k, 10 mile,
              Half-Marathon, Marathon, 50k
- Informations athlète (nom, id)

Ce qui N'EST PAS disponible via l'API Strava :
- Endpoint dédié /records — n'existe pas
- Records all-time sans parcourir les activités une par une
- Prédictions de course (Strava n'expose pas de modèle prédictif)
- Best efforts sans appeler le détail de chaque activité
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import requests

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Noms Strava des best_efforts → distance en km (correspondance exacte avec TARGETS dans Records)
STRAVA_EFFORT_DISTANCES: dict[str, float] = {
    "400m":          0.4,
    "1/2 mile":      0.80467,
    "1k":            1.0,
    "1 mile":        1.60934,
    "2 mile":        3.21869,
    "5k":            5.0,
    "10k":           10.0,
    "10 mile":       16.0934,
    "Half-Marathon": 21.0975,
    "Marathon":      42.195,
    "50k":           50.0,
}


def get_auth_url(client_id: str, redirect_uri: str) -> str:
    """Construit l'URL d'autorisation OAuth Strava."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "activity:read_all",
        "approval_prompt": "auto",
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    """Échange le code OAuth contre access_token + refresh_token."""
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _do_refresh(client_id: str, client_secret: str, refresh_tok: str) -> dict:
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_tok,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_valid_access_token(credentials: dict) -> str:
    """Retourne un access_token valide, rafraîchi si expiré."""
    if credentials.get("expires_at", 0) > time.time() + 60:
        return credentials["access_token"]

    new_tokens = _do_refresh(
        credentials["client_id"],
        credentials["client_secret"],
        credentials["refresh_token"],
    )
    from src.storage import save_strava_credentials
    save_strava_credentials({**credentials, **new_tokens})
    return new_tokens["access_token"]


def _api_get(
    access_token: str,
    path: str,
    params: Optional[dict] = None,
) -> dict | list | None:
    """Appel GET Strava avec gestion des erreurs courantes."""
    resp = requests.get(
        f"{STRAVA_API_BASE}/{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params or {},
        timeout=30,
    )
    if resp.status_code == 401:
        raise ValueError("Token Strava invalide ou expiré. Reconnectez-vous.")
    if resp.status_code == 429:
        raise RuntimeError("Limite de requêtes Strava atteinte (100/15 min). Réessayez dans 15 minutes.")
    if not resp.ok:
        return None
    return resp.json()


def fetch_activity_summaries(
    access_token: str,
    max_activities: int = 500,
) -> list[dict]:
    """Récupère les résumés d'activités running/trail (sans best_efforts)."""
    result: list[dict] = []
    page = 1
    while len(result) < max_activities:
        per_page = min(100, max_activities - len(result))
        batch = _api_get(access_token, "athlete/activities", {"page": page, "per_page": per_page})
        if not batch:
            break
        running = [a for a in batch if a.get("type") in ("Run", "TrailRun")]
        result.extend(running)
        if len(batch) < per_page:
            break
        page += 1
    return result[:max_activities]


def fetch_activity_detail(access_token: str, activity_id: int) -> dict | None:
    """Récupère le détail d'une activité, incluant les best_efforts."""
    return _api_get(access_token, f"activities/{activity_id}")


def _extract_best_efforts(
    detail: dict,
    summary: dict,
    records: dict[float, dict],
) -> None:
    """Met à jour records avec les best_efforts de cette activité si meilleurs."""
    for effort in detail.get("best_efforts") or []:
        name = effort.get("name", "")
        dist_km = STRAVA_EFFORT_DISTANCES.get(name)
        if dist_km is None:
            continue

        t_s = effort.get("elapsed_time") or effort.get("moving_time")
        if not t_s or t_s <= 0:
            continue

        date_raw = effort.get("start_date_local") or summary.get("start_date_local", "")
        try:
            date_str = datetime.fromisoformat(date_raw.replace("Z", "")).strftime("%d/%m/%Y")
        except Exception:
            date_str = "—"

        if dist_km not in records or float(t_s) < records[dist_km]["time_s"]:
            records[dist_km] = {
                "time_s": float(t_s),
                "date": date_str,
                "activity_id": summary["id"],
                "activity_name": summary.get("name", ""),
                "source": "Strava",
            }


def fetch_strava_records(
    credentials: dict,
    max_detail_calls: int = 50,
    progress_callback=None,
) -> dict[float, dict]:
    """
    Construit les records personnels en scannant les best_efforts des activités Strava.

    Stratégie :
    - Récupère jusqu'à 500 résumés d'activités running
    - Priorise celles avec achievement_count > 0 (contiennent probablement des PRs)
    - Appelle le détail pour au plus max_detail_calls activités
    - Pour chaque best_effort, conserve le meilleur temps par distance

    Limite : ne couvre que les activités récentes, pas l'historique complet.
    Strava rate limit : 100 req/15 min, 1000 req/jour.

    Retourne : {distance_km: {time_s, date, activity_id, activity_name, source}}
    """
    access_token = get_valid_access_token(credentials)
    summaries = fetch_activity_summaries(access_token)

    # Priorité aux activités avec des achievements (plus susceptibles d'avoir des PRs)
    with_ach = [a for a in summaries if (a.get("achievement_count") or 0) > 0]
    without_ach = [a for a in summaries if (a.get("achievement_count") or 0) == 0]
    to_fetch = (with_ach + without_ach)[:max_detail_calls]

    records: dict[float, dict] = {}

    for i, activity in enumerate(to_fetch):
        try:
            detail = fetch_activity_detail(access_token, activity["id"])
            if detail:
                _extract_best_efforts(detail, activity, records)
        except RuntimeError:
            # Rate limit hit — on s'arrête proprement avec ce qu'on a
            break
        except Exception:
            continue

        if progress_callback:
            progress_callback(i + 1, len(to_fetch))

    return records
