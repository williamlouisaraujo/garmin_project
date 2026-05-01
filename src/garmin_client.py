import streamlit as st
from garminconnect import Garmin, GarminConnectAuthenticationError


@st.cache_resource(ttl=3600, show_spinner=False)
def _get_client(email: str, password: str) -> Garmin:
    """Connexion Garmin Connect, mise en cache 1h par compte."""
    try:
        client = Garmin(email, password)
        client.login()
        return client
    except GarminConnectAuthenticationError as exc:
        raise ValueError(f"Identifiants incorrects pour {email} : {exc}") from exc


def fetch_activities(email: str, password: str, limit: int = 200) -> list[dict]:
    """Récupère les <limit> dernières activités depuis Garmin Connect."""
    client = _get_client(email, password)
    return client.get_activities(0, limit)
