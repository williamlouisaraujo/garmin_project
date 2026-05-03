"""
Strava OAuth 2.0 integration.

Ce qui est disponible via l'API Strava :
- best_efforts par distance standard sur chaque activité détaillée
- Informations athlète (nom, id)

Ce qui N'EST PAS disponible via l'API Strava :
- Endpoint dédié /records — n'existe pas
- Records all-time sans parcourir les activités une par une
- Prédictions de course (Strava n'expose pas de modèle prédictif)
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlencode

import requests

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_auth_url(client_id: str, redirect_uri: str, state: str = "") -> str:
    """
    Construit l'URL d'autorisation OAuth Strava.
    state : identifiant à passer en clair (ex: garmin_email) pour retrouver
            quel compte Garmin lier au retour du redirect.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "activity:read_all",
        "approval_prompt": "auto",
    }
    if state:
        params["state"] = state
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


def get_valid_access_token(app_config: dict, account: dict) -> str:
    """
    Retourne un access_token valide, en le rafraîchissant si expiré.

    app_config : {client_id, client_secret}  — config partagée de l'app Strava
    account    : {garmin_email, access_token, refresh_token, expires_at, …}
    """
    if account.get("expires_at", 0) > time.time() + 60:
        return account["access_token"]

    new_tokens = _do_refresh(
        app_config["client_id"],
        app_config["client_secret"],
        account["refresh_token"],
    )
    from src.storage import save_strava_account
    save_strava_account({**account, **new_tokens})
    return new_tokens["access_token"]


