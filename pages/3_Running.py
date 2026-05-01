import pandas as pd
import streamlit as st

from src.auth import require_password
from src.storage import get_accounts, get_activities_df
from src.transform import compute_vap, format_duration, format_pace

st.set_page_config(page_title="Historique des activités", page_icon="📋", layout="wide")
require_password()

st.title("📋 Historique des activités")

# ── Chargement ────────────────────────────────────────────────────────────────
try:
    df = get_activities_df()
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.stop()

if df.empty:
    st.info("Aucune activité. Synchronise depuis la page Connexion.")
    st.stop()

df["start_time"] = pd.to_datetime(df["start_time"])

# ── Filtres ───────────────────────────────────────────────────────────────────
ncols = 3 if len(accounts) > 1 else 2
filter_cols = st.columns(ncols)

with filter_cols[0]:
    types_dispo = sorted(df["type"].dropna().unique().tolist())
    types_choisis = st.multiselect("Type d'activité", types_dispo, default=types_dispo)

with filter_cols[1]:
    min_date = df["start_time"].min().date()
    max_date = df["start_time"].max().date()
    periode = st.date_input("Période", value=(min_date, max_date))

selected_account = None
if len(accounts) > 1:
    account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}
    with filter_cols[2]:
        choix = st.selectbox("Utilisateur", ["Tous"] + list(account_labels.values()))
    if choix != "Tous":
        selected_account = next(e for e, lbl in account_labels.items() if lbl == choix)

# ── Application des filtres ───────────────────────────────────────────────────
mask = df["type"].isin(types_choisis)
if isinstance(periode, (list, tuple)) and len(periode) == 2:
    mask &= df["start_time"].dt.date >= periode[0]
    mask &= df["start_time"].dt.date <= periode[1]
if selected_account:
    mask &= df["garmin_account"] == selected_account

df_f = df[mask].copy()
st.caption(f"**{len(df_f)} activité(s)**")

# ── Construction du tableau ───────────────────────────────────────────────────
display = df_f[
    ["start_time", "name", "type", "distance_km", "duration_min",
     "pace_min_km", "elevation_m", "avg_hr", "calories", "garmin_account"]
].copy()

display["Date"] = display["start_time"].dt.strftime("%d/%m/%Y")
display["Durée"] = display["duration_min"].apply(format_duration)
display["Allure"] = display["pace_min_km"].apply(format_pace)
display["VAP"] = display.apply(
    lambda r: format_pace(compute_vap(r["pace_min_km"], r["elevation_m"], r["distance_km"])),
    axis=1,
)
display["D+ (m)"] = display["elevation_m"].fillna(0).astype(int)
display["FC moy"] = display["avg_hr"].where(display["avg_hr"].notna() & (display["avg_hr"] > 0))

display = display.rename(columns={
    "name": "Activité",
    "type": "Type",
    "distance_km": "Dist. (km)",
    "calories": "Cal",
})

colonnes = ["Date", "Activité", "Type", "Dist. (km)", "Durée", "Allure", "VAP", "D+ (m)", "FC moy", "Cal"]

if len(accounts) > 1 and selected_account is None:
    account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}
    display["Utilisateur"] = df_f["garmin_account"].map(account_labels).fillna(df_f["garmin_account"])
    colonnes = ["Utilisateur"] + colonnes

st.dataframe(
    display[colonnes],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Dist. (km)": st.column_config.NumberColumn(format="%.2f km"),
        "FC moy": st.column_config.NumberColumn(format="%d bpm"),
        "Cal": st.column_config.NumberColumn(format="%d kcal"),
        "D+ (m)": st.column_config.NumberColumn(format="%d m"),
    },
)
