import pandas as pd
import streamlit as st

from src.auth import require_password
from src.storage import get_activities_df
from src.transform import format_duration, format_pace

st.set_page_config(page_title="Running", page_icon="🏃", layout="wide")
require_password()

st.title("🏃 Running")
st.caption("Historique de tes activités")

df = get_activities_df()

if df.empty:
    st.info("Aucune activité. Synchronise depuis la page Accueil.")
    st.stop()

df["start_time"] = pd.to_datetime(df["start_time"])

# ── Filtres ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    types_dispo = sorted(df["type"].dropna().unique().tolist())
    types_choisis = st.multiselect("Type d'activité", types_dispo, default=types_dispo)

with col2:
    min_date = df["start_time"].min().date()
    max_date = df["start_time"].max().date()
    periode = st.date_input("Période", value=(min_date, max_date))

# ── Application des filtres ───────────────────────────────────────────────────
mask = df["type"].isin(types_choisis)
if isinstance(periode, (list, tuple)) and len(periode) == 2:
    mask &= df["start_time"].dt.date >= periode[0]
    mask &= df["start_time"].dt.date <= periode[1]

df_f = df[mask].copy()
st.caption(f"**{len(df_f)} activité(s)**")

# ── Tableau ───────────────────────────────────────────────────────────────────
display = df_f[
    ["start_time", "name", "type", "distance_km", "duration_min",
     "pace_min_km", "elevation_m", "avg_hr", "calories"]
].copy()

display["Date"] = display["start_time"].dt.strftime("%d/%m/%Y")
display["Durée"] = display["duration_min"].apply(format_duration)
display["Allure"] = display["pace_min_km"].apply(format_pace)
display["D+ (m)"] = display["elevation_m"].fillna(0).astype(int)
display["FC moy"] = display["avg_hr"].fillna(0).astype(int).replace(0, None)

display = display.rename(columns={
    "name": "Activité",
    "type": "Type",
    "distance_km": "Dist. (km)",
    "calories": "Cal",
})

colonnes = ["Date", "Activité", "Type", "Dist. (km)", "Durée", "Allure", "D+ (m)", "FC moy", "Cal"]
st.dataframe(
    display[colonnes],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Dist. (km)": st.column_config.NumberColumn(format="%.2f km"),
        "Cal": st.column_config.NumberColumn(format="%d kcal"),
    },
)
