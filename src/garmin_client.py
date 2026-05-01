import os

import streamlit as st
from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectAuthenticationError

load_dotenv()


def _get_credentials() -> tuple[str, str]:
    try:
        email = st.secrets.get("GARMIN_EMAIL") or os.getenv("GARMIN_EMAIL", "")
        password = st.secrets.get("GARMIN_PASSWORD") or os.getenv("GARMIN_PASSWORD", "")
    except Exception:
        email = os.getenv("GARMIN_EMAIL", "")
        password = os.getenv("GARMIN_PASSWORD", "")
    return email, password


@st.cache_resource(ttl=3600, show_spinner=False)
def _get_client() -> Garmin:
    """Connexion Garmin Connect, mise en cache 1h pour éviter les re-logins."""
    email, password = _get_credentials()
    if not email or not password:
        raise ValueError(
            "GARMIN_EMAIL et GARMIN_PASSWORD sont requis.\n"
            "Renseigne-les dans .streamlit/secrets.toml ou dans un fichier .env."
        )
    try:
        client = Garmin(email, password)
        client.login()
        return client
    except GarminConnectAuthenticationError as exc:
        raise ValueError(f"Identifiants Garmin incorrects : {exc}") from exc


def fetch_activities(limit: int = 200) -> list[dict]:
    """Récupère les <limit> dernières activités depuis Garmin Connect."""
    client = _get_client()
    return client.get_activities(0, limit)
