import streamlit as st

from src.auth import require_password
from src.garmin_client import fetch_activities
from src.storage import get_sync_summary, save_activities

st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="🏃",
    layout="wide",
)

require_password()

st.title("🏠 Accueil")
st.caption("Dashboard personnel Garmin Connect")

# ── Bouton synchronisation ────────────────────────────────────────────────────
with st.container():
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        sync = st.button("🔄 Synchroniser Garmin", use_container_width=True)
    with col_info:
        st.caption("Récupère les 200 dernières activités. Les activités déjà présentes sont ignorées.")

if sync:
    with st.spinner("Connexion à Garmin Connect…"):
        try:
            activities = fetch_activities(limit=200)
            count_new = save_activities(activities)
            if count_new > 0:
                st.success(f"✅ Synchronisation terminée — {count_new} nouvelle(s) activité(s) ajoutée(s).")
            else:
                st.info("✅ Déjà à jour, aucune nouvelle activité.")
        except ValueError as exc:
            st.error(f"⚠️ Configuration : {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"❌ Erreur Garmin Connect : {exc}")
            st.stop()

st.divider()

# ── KPIs ──────────────────────────────────────────────────────────────────────
try:
    summary = get_sync_summary()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.info("Vérifie que SUPABASE_URL et SUPABASE_KEY sont bien configurées dans les Secrets Streamlit Cloud.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Dernière synchro", summary["last_sync"])
col2.metric("Activités totales", summary["total_activities"])

col3, col4, col5 = st.columns(3)
col3.metric("Distance totale", f"{summary['total_distance_km']:,.0f} km")
col4.metric("Dénivelé total", f"{summary['total_elevation_m']:,} m D+")
col5.metric("Durée totale", f"{summary['total_duration_h']:.0f} h")

st.divider()
st.info("👈 Utilise le menu de gauche pour accéder aux pages Running et Tendances.")
