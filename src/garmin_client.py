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
    """Récupère les <limit> dernières activités (une seule requête)."""
    client = _get_client(email, password)
    return client.get_activities(0, limit)


def fetch_all_activities(
    email: str,
    password: str,
    batch_size: int = 100,
    max_activities: int = 10_000,
    progress_callback=None,
) -> list[dict]:
    """Récupère tout l'historique par pagination (batches de <batch_size>)."""
    client = _get_client(email, password)
    all_activities: list[dict] = []
    start = 0

    while len(all_activities) < max_activities:
        to_fetch = min(batch_size, max_activities - len(all_activities))
        batch = client.get_activities(start, to_fetch)
        if not batch:
            break
        all_activities.extend(batch)
        if progress_callback:
            progress_callback(len(all_activities))
        if len(batch) < to_fetch:
            break
        start += to_fetch

    return all_activities
