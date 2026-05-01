import streamlit as st
from src.database import get_latest_sync_summary

st.set_page_config(page_title="My Personal Garmin Dashboard", page_icon="🏃", layout="wide")


def require_password() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    with st.form("login"):
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        if password == st.secrets.get("APP_PASSWORD", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")
    st.stop()


require_password()

st.title("🏠 Accueil")
st.caption("Dashboard personnel Garmin + santé")

summary = get_latest_sync_summary()

col1, col2, col3 = st.columns(3)
col1.metric("Dernière synchro", summary["last_sync"])
col2.metric("KM semaine", f"{summary['weekly_km']:.1f} km")
col3.metric("D+ semaine", f"{summary['weekly_elevation']} m")

col4, col5, col6 = st.columns(3)
col4.metric("Sommeil", f"{summary['sleep_hours']:.1f} h")
col5.metric("HRV", f"{summary['hrv']} ms")
col6.metric("Fatigue estimée", summary["fatigue"])

st.info("Utilise le menu de gauche pour naviguer entre Running, Stats, Recovery, Training plan et Settings.")
