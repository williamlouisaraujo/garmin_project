import streamlit as st

from src.auth import require_password

st.set_page_config(page_title="Paramètres", page_icon="⚙️", layout="wide")
require_password()

st.title("⚙️ Paramètres")

st.info(
    "La gestion des comptes Garmin (ajout, suppression, synchronisation) "
    "se fait depuis la page **Connexion & Synchronisation** (accueil)."
)

st.divider()
st.subheader("Informations")
st.markdown("""
- Les credentials Garmin sont stockés dans **Supabase** (table `settings`), jamais dans le code.
- La connexion à Supabase est configurée via les **Secrets Streamlit Cloud** (`SUPABASE_URL`, `SUPABASE_KEY`).
- Le mot de passe d'accès à l'app est défini via le secret `APP_PASSWORD`.
""")
