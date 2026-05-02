from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src.storage import get_accounts, get_activities_df
from src.transform import format_duration, format_pace

st.title("📊 Stats globales")

# ── Chargement ────────────────────────────────────────────────────────────────
try:
    df_all = get_activities_df()
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.stop()

if df_all.empty:
    st.info("Aucune activité. Synchronisez depuis la page Connexion.")
    st.stop()

df_all["start_time"] = pd.to_datetime(df_all["start_time"])

# ── Filtre compte ─────────────────────────────────────────────────────────────
account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}
account_emails = list(account_labels.keys())

if len(accounts) > 1:
    options = [account_labels[e] for e in account_emails]
    choix = st.selectbox("Compte", options)
    selected_account = next(e for e in account_emails if account_labels[e] == choix)
else:
    selected_account = account_emails[0] if account_emails else None

df = df_all if selected_account is None else df_all[df_all["garmin_account"] == selected_account]

# ── Périodes ──────────────────────────────────────────────────────────────────
now = datetime.now()
start_of_year = datetime(now.year, 1, 1)
start_of_month = datetime(now.year, now.month, 1)
start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

periods = {
    "Depuis toujours": df,
    "Cette année": df[df["start_time"] >= start_of_year],
    "Ce mois-ci": df[df["start_time"] >= start_of_month],
    "Cette semaine": df[df["start_time"] >= start_of_week],
}


def compute_stats(period_df: pd.DataFrame) -> dict:
    if period_df.empty:
        return {
            "activités": 0,
            "distance": "0 km",
            "dénivelé": "0 m D+",
            "allure": "—",
            "bpm": "—",
            "durée": "—",
        }
    with_distance = period_df[period_df["distance_km"] > 0.1]
    avg_pace = with_distance["pace_min_km"].dropna().mean() if not with_distance.empty else None
    hr_vals = period_df["avg_hr"].dropna()
    avg_bpm = hr_vals.mean() if not hr_vals.empty else None

    return {
        "activités": len(period_df),
        "distance": f"{period_df['distance_km'].sum():,.1f} km",
        "dénivelé": f"{int(period_df['elevation_m'].sum()):,} m D+",
        "allure": format_pace(avg_pace),
        "bpm": f"{int(avg_bpm)} bpm" if avg_bpm else "—",
        "durée": format_duration(period_df["duration_min"].sum()),
    }


tabs = st.tabs(list(periods.keys()))

for tab, (period_name, period_df) in zip(tabs, periods.items()):
    with tab:
        stats = compute_stats(period_df)
        col1, col2, col3 = st.columns(3)
        col1.metric("Activités", stats["activités"])
        col2.metric("Distance", stats["distance"])
        col3.metric("Dénivelé", stats["dénivelé"])

        col4, col5, col6 = st.columns(3)
        col4.metric("Allure moy.", stats["allure"])
        col5.metric("BPM moy.", stats["bpm"])
        col6.metric("Durée totale", stats["durée"])

# ── Comparaison multi-comptes ─────────────────────────────────────────────────
if len(accounts) > 1:
    st.divider()
    st.subheader("Comparaison des comptes (toutes périodes)")

    rows = []
    for acc in accounts:
        acc_df = df_all[df_all["garmin_account"] == acc["email"]]
        s = compute_stats(acc_df)
        rows.append({
            "Compte": acc.get("label", acc["email"]),
            "Activités": s["activités"],
            "Distance": s["distance"],
            "Dénivelé": s["dénivelé"],
            "Allure moy.": s["allure"],
            "BPM moy.": s["bpm"],
            "Durée totale": s["durée"],
        })

    st.dataframe(pd.DataFrame(rows).set_index("Compte"), use_container_width=True)
