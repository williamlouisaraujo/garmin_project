import streamlit as st
from datetime import date as _date
from garminconnect import Garmin, GarminConnectAuthenticationError


_ALLOWED_ACTIVITY_TYPES = {"running", "trail_running"}


def _extract_type_key(activity: dict) -> str:
    activity_type = activity.get("activityType") if isinstance(activity, dict) else None
    if isinstance(activity_type, dict):
        return str(activity_type.get("typeKey") or "").strip().lower()
    if isinstance(activity_type, str):
        return activity_type.strip().lower()
    return ""


def _filter_allowed_activities(activities: list[dict]) -> list[dict]:
    return [a for a in activities if _extract_type_key(a) in _ALLOWED_ACTIVITY_TYPES]


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
    activities = client.get_activities(0, limit)
    return _filter_allowed_activities(activities)


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

    return _filter_allowed_activities(all_activities)


def _safe_call(fn, *args, **kwargs):
    """Appelle fn et retourne None en cas d'erreur."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        st.warning(f"Garmin API call failed ({getattr(fn, '__name__', 'unknown')}): {exc}")
        return None



def get_vo2max_data(email: str, password: str, cdate: str | None = None) -> dict | None:
    """VO2max et métriques de forme via get_max_metrics()."""
    client = _get_client(email, password)
    cdate = cdate or _date.today().isoformat()
    return _safe_call(client.get_max_metrics, cdate)


def get_vo2max_data_last_days(email: str, password: str, days: int = 30) -> list[dict]:
    """Retourne les métriques max des derniers jours (du plus récent au plus ancien)."""
    client = _get_client(email, password)
    out: list[dict] = []
    for i in range(days):
        d = (_date.today()).fromordinal(_date.today().toordinal() - i).isoformat()
        data = _safe_call(client.get_max_metrics, d)
        if data:
            out.append(data)
    return out


def get_lactate_threshold_data(email: str, password: str) -> dict | None:
    """Seuil lactique natif Garmin (dernier connu)."""
    client = _get_client(email, password)
    return _safe_call(client.get_lactate_threshold, latest=True)


def get_user_profile_data(email: str, password: str) -> dict | None:
    """Paramètres utilisateur (FCmax, FC repos, âge…)."""
    client = _get_client(email, password)
    return _safe_call(client.get_userprofile_settings)


def get_training_readiness_data(email: str, password: str, cdate: str | None = None) -> dict | None:
    """Score de forme du jour."""
    client = _get_client(email, password)
    cdate = cdate or _date.today().isoformat()
    return _safe_call(client.get_training_readiness, cdate)


def get_personal_records_native(email: str, password: str) -> list | dict | None:
    """Records personnels natifs Garmin Connect."""
    client = _get_client(email, password)
    return _safe_call(client.get_personal_record)


def get_race_predictions_native(email: str, password: str) -> dict | list | None:
    """Prédictions de course natives Garmin Connect (dernières en date)."""
    client = _get_client(email, password)
    return _safe_call(client.get_race_predictions)