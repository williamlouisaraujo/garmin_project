import streamlit as st

from src.auth import require_password
from src.charts import weekly_count_chart, weekly_distance_chart, weekly_elevation_chart
from src.storage import get_activities_df
from src.transform import weekly_aggregation

st.set_page_config(page_title="Tendances", page_icon="📊", layout="wide")
require_password()

st.title("📊 Tendances")
st.caption("Évolution hebdomadaire de tes activités")

df = get_activities_df()

if df.empty:
    st.info("Aucune activité. Synchronise depuis la page Accueil.")
    st.stop()

weekly = weekly_aggregation(df)

# ── Filtre semaines ───────────────────────────────────────────────────────────
n_semaines = st.slider("Nombre de semaines à afficher", min_value=4, max_value=52, value=12, step=4)
weekly_display = weekly.tail(n_semaines)

# ── Graphiques ────────────────────────────────────────────────────────────────
fig_dist = weekly_distance_chart(weekly_display)
fig_elev = weekly_elevation_chart(weekly_display)
fig_count = weekly_count_chart(weekly_display)

if fig_dist:
    st.plotly_chart(fig_dist, use_container_width=True)

if fig_elev:
    st.plotly_chart(fig_elev, use_container_width=True)

if fig_count:
    st.plotly_chart(fig_count, use_container_width=True)

# ── Tableau récap hebdo ───────────────────────────────────────────────────────
with st.expander("Détail par semaine"):
    recap = weekly_display[["week_label", "distance_km", "elevation_m", "count"]].copy()
    recap = recap.rename(columns={
        "week_label": "Semaine",
        "distance_km": "Distance (km)",
        "elevation_m": "D+ (m)",
        "count": "Sorties",
    })
    st.dataframe(recap, use_container_width=True, hide_index=True)
