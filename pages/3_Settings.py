import streamlit as st

from src.auth import require_password
from src.storage import get_setting, save_setting

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
require_password()

st.title("⚙️ Paramètres")
st.caption("Configure tes identifiants Garmin Connect")

# ── État actuel ───────────────────────────────────────────────────────────────
current_email = get_setting("garmin_email") or ""

if current_email:
    st.success(f"Compte Garmin configuré : **{current_email}**")
else:
    st.warning("Aucun compte Garmin configuré. Renseigne tes identifiants ci-dessous.")

st.divider()

# ── Formulaire ────────────────────────────────────────────────────────────────
st.subheader("Identifiants Garmin Connect")
st.caption("Stockés dans Supabase, jamais dans le code.")

with st.form("garmin_credentials"):
    email = st.text_input(
        "Email Garmin Connect",
        value=current_email,
        placeholder="ton@email.com",
    )
    password = st.text_input(
        "Mot de passe Garmin Connect",
        type="password",
        placeholder="Laisse vide pour conserver le mot de passe actuel",
    )
    submitted = st.form_submit_button("💾 Enregistrer", use_container_width=True)

if submitted:
    if not email:
        st.error("L'email est requis.")
    else:
        save_setting("garmin_email", email)
        if password:
            save_setting("garmin_password", password)
        # Force le re-login Garmin avec les nouveaux credentials
        st.cache_resource.clear()
        st.success("✅ Paramètres enregistrés. Tu peux maintenant synchroniser depuis l'Accueil.")
