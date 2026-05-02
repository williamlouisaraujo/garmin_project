import streamlit as st

from src.auth import require_password

st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="🏃",
    layout="wide",
)

require_password()

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
pg.run()
