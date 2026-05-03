from urllib.parse import unquote

import streamlit as st

from src.auth import require_password

st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="🏃",
    layout="wide",
)

# ── Capture du code OAuth Strava avant la porte d'authentification ─────────────
# Strava redirige avec ?code=XXX&state=garmin_email.
# Dans un nouvel onglet, require_password() appelle st.stop() AVANT que
# st.navigation() soit initialisé, ce qui ferait perdre les query_params.
# On sauvegarde donc le code en session_state dès le premier run.
if "code" in st.query_params and "_strava_oauth_code" not in st.session_state:
    st.session_state["_strava_oauth_code"] = st.query_params["code"]
    st.session_state["_strava_oauth_state"] = st.query_params.get("state", "")

require_password()

# ── Traitement du code OAuth Strava après authentification ────────────────────
# On traite ici (dans app.py) pour que ça fonctionne quelle que soit la page
# sur laquelle Streamlit atterrit après le mot de passe.
if st.session_state.get("_strava_oauth_code"):
    _code = st.session_state.pop("_strava_oauth_code")
    _state_email = unquote(st.session_state.pop("_strava_oauth_state", ""))

    try:
        from src.storage import get_strava_app_config, save_strava_account
        from src.strava_client import exchange_code as _strava_exchange

        _cfg = get_strava_app_config()
        if _cfg and _state_email:
            _tokens = _strava_exchange(_cfg["client_id"], _cfg["client_secret"], _code)
            _athlete = _tokens.get("athlete") or {}
            save_strava_account({
                "garmin_email": _state_email,
                "access_token": _tokens["access_token"],
                "refresh_token": _tokens["refresh_token"],
                "expires_at": _tokens.get("expires_at", 0),
                "athlete": _athlete,
            })
            _name = f"{_athlete.get('firstname', '')} {_athlete.get('lastname', '')}".strip()
            st.session_state["_strava_connect_success"] = _state_email
            st.session_state["_strava_connect_athlete"] = _name or _state_email
        else:
            st.session_state["_strava_connect_error"] = (
                "Configuration Strava introuvable ou compte Garmin non identifié (state vide)."
            )
    except Exception as _exc:
        st.session_state["_strava_connect_error"] = str(_exc)

    st.query_params.clear()

pg = st.navigation(
    {
        "Data Visualisation": [
            st.Page("pages/1_Stats_globales.py", title="Stats Globales", icon="📊"),
            st.Page("pages/2_Forme_actuelle.py", title="Forme actuelle", icon="💪"),
            st.Page("pages/3_Running.py", title="Liste des activités", icon="📋"),
            st.Page("pages/4_Tendances.py", title="Vision hebdo", icon="📈"),
            st.Page("pages/6_Records.py", title="Records & Prédictions", icon="🏆"),
            st.Page("pages/7_Programme.py", title="Programme d'entraînement", icon="📅"),
        ],
        "Réglages": [
            st.Page("pages/sync.py", title="Synchronisation", icon="🔗"),
            st.Page("pages/5_Settings.py", title="Réglages", icon="⚙️"),
        ],
    }
)

# Redirige vers la page Synchronisation après une connexion Strava réussie
# (l'utilisateur atterrit souvent sur Stats globales après le mot de passe)
if st.session_state.get("_strava_connect_success") or st.session_state.get("_strava_connect_error"):
    st.switch_page("pages/sync.py")

pg.run()
