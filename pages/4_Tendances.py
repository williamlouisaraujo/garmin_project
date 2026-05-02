import streamlit as st

from src.charts import weekly_count_chart, weekly_distance_chart, weekly_elevation_chart
from src.storage import get_accounts, get_activities_df
from src.transform import weekly_aggregation

st.title("📈 Vision hebdo")
st.caption("Évolution hebdomadaire de tes activités")

# ── Chargement ────────────────────────────────────────────────────────────────
try:
    df_all = get_activities_df()
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.stop()

if df_all.empty:
    st.info("Aucune activité. Synchronise depuis la page Connexion.")
    st.stop()

# ── Filtre compte ─────────────────────────────────────────────────────────────
if len(accounts) > 1:
    account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}
    choix = st.selectbox("Utilisateur", list(account_labels.values()))
    selected_email = next(e for e, lbl in account_labels.items() if lbl == choix)
    df = df_all[df_all["garmin_account"] == selected_email]
elif accounts:
    df = df_all[df_all["garmin_account"] == accounts[0]["email"]]
else:
    df = df_all

weekly = weekly_aggregation(df)

# ── Filtre semaines ───────────────────────────────────────────────────────────
n_semaines = st.slider("Nombre de semaines à afficher", min_value=4, max_value=min(52, len(weekly)), value=min(12, len(weekly)), step=4)
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
