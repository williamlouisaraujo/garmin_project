import streamlit as st

st.title("⚙️ Réglages")

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
