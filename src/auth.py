import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def require_password() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    st.title("🔒 Connexion")

    with st.form("login"):
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        try:
            expected = st.secrets.get("APP_PASSWORD") or os.getenv("APP_PASSWORD", "")
        except Exception:
            expected = os.getenv("APP_PASSWORD", "")

        if password and password == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")

    st.stop()
