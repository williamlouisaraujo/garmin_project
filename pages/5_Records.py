from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import require_password
from src.storage import get_accounts, get_activities_df
from src.transform import format_duration_hms, format_pace

st.set_page_config(page_title="Records", page_icon="🏆", layout="wide")
require_password()

st.title("🏆 Records & Prédictions")
st.caption("Meilleurs temps par distance et prédictions basées sur la formule de Riegel.")

# ── Distances cibles ──────────────────────────────────────────────────────────
TARGETS: list[tuple[str, float, float, float]] = [
    # label, distance_km, tolerance_low, tolerance_high
    ("500 m",        0.5,   0.40,  0.60),
    ("1 km",         1.0,   0.90,  1.10),
    ("5 km",         5.0,   4.70,  5.30),
    ("10 km",       10.0,   9.50, 10.50),
    ("Semi-marathon", 21.0975, 20.0, 22.5),
    ("30 km",       30.0,  28.0,  32.0),
    ("Marathon",    42.195, 41.0,  43.5),
    ("50 km",       50.0,  47.0,  53.0),
    ("100 km",     100.0,  95.0, 105.0),
]


def riegel(t1_s: float, d1_km: float, d2_km: float) -> int:
    """T2 = T1 * (D2/D1)^1.06  — formule de Riegel."""
    return int(t1_s * (d2_km / d1_km) ** 1.06)


def best_activity_for_distance(
    df: pd.DataFrame, low_km: float, high_km: float
) -> dict | None:
    """Retourne l'activité avec le meilleur temps sur la plage de distance donnée."""
    mask = (df["distance_km"] >= low_km) & (df["distance_km"] <= high_km) & (df["duration_min"] > 0)
    candidates = df[mask].copy()
    if candidates.empty:
        return None
    candidates["pace"] = candidates["duration_min"] / candidates["distance_km"]
    best = candidates.loc[candidates["pace"].idxmin()]
    return best.to_dict()


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

df_all["start_time"] = pd.to_datetime(df_all["start_time"])

# ── Filtre compte ─────────────────────────────────────────────────────────────
account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}

if len(accounts) > 1:
    options = ["Tous les comptes"] + [account_labels.get(a["email"], a["email"]) for a in accounts]
    choix = st.selectbox("Utilisateur", options)
    if choix == "Tous les comptes":
        selected_df = df_all
        selected_label = "Tous"
    else:
        selected_email = next(e for e, lbl in account_labels.items() if lbl == choix)
        selected_df = df_all[df_all["garmin_account"] == selected_email]
        selected_label = choix
else:
    selected_df = df_all
    selected_label = accounts[0].get("label", accounts[0]["email"]) if accounts else "—"

# ── Calcul des records ────────────────────────────────────────────────────────
records: list[dict] = []
for label, dist_km, low, high in TARGETS:
    best = best_activity_for_distance(selected_df, low, high)
    records.append({
        "_label": label,
        "_dist_km": dist_km,
        "_best": best,
    })

# Trouver la meilleure référence pour les prédictions (distance la mieux couverte)
ref = None
ref_priority = [5.0, 10.0, 21.0975, 42.195, 1.0, 0.5, 30.0, 50.0, 100.0]
for ref_dist in ref_priority:
    for r in records:
        if abs(r["_dist_km"] - ref_dist) < 0.1 and r["_best"] is not None:
            ref = r
            break
    if ref:
        break

# ── Affichage ─────────────────────────────────────────────────────────────────
rows = []
for r in records:
    label = r["_label"]
    dist_km = r["_dist_km"]
    best = r["_best"]

    if best is not None:
        t_s = int(best["duration_min"] * 60)
        actual_dist = best["distance_km"]
        # Normalise le temps à la distance exacte cible
        t_s_norm = int(t_s * dist_km / actual_dist) if actual_dist > 0 else t_s
        record_str = format_duration_hms(t_s_norm)
        pace_str = format_pace(t_s_norm / 60 / dist_km)
        date_str = pd.to_datetime(best["start_time"]).strftime("%d/%m/%Y") if best.get("start_time") else "—"
        activity_name = best.get("name", "—")
    else:
        record_str = "—"
        pace_str = "—"
        date_str = "—"
        activity_name = "—"
        t_s_norm = None

    # Prédiction Riegel
    if ref is not None and ref["_best"] is not None:
        ref_best = ref["_best"]
        ref_t_s = int(ref_best["duration_min"] * 60)
        ref_actual_dist = ref_best["distance_km"]
        ref_t_s_norm = int(ref_t_s * ref["_dist_km"] / ref_actual_dist)
        pred_s = riegel(ref_t_s_norm, ref["_dist_km"], dist_km)
        pred_str = format_duration_hms(pred_s)
        pred_pace_str = format_pace(pred_s / 60 / dist_km)
    else:
        pred_str = "—"
        pred_pace_str = "—"

    rows.append({
        "Distance": label,
        "Record": record_str,
        "Allure": pace_str,
        "Date": date_str,
        "Activité": activity_name,
        "Prédiction Riegel": pred_str,
        "Allure préd.": pred_pace_str,
    })

df_records = pd.DataFrame(rows)

if ref:
    ref_label = next((t[0] for t in TARGETS if abs(t[1] - ref["_dist_km"]) < 0.1), "")
    st.caption(f"Prédictions calculées à partir du record sur **{ref_label}**.")

st.dataframe(df_records, use_container_width=True, hide_index=True)

st.caption(
    "**Record** : meilleure performance sur une activité à la distance cible (±10-15%). "
    "**Prédiction** : estimation basée sur la formule de Riegel T₂ = T₁ × (D₂/D₁)^1.06. "
    "**VAP non prise en compte** dans les records (temps brut d'activité)."
)

# ── Comparaison multi-comptes ─────────────────────────────────────────────────
if len(accounts) > 1:
    st.divider()
    st.subheader("Comparaison des records entre utilisateurs")

    comp_rows: list[dict] = []
    for label, dist_km, low, high in TARGETS:
        row: dict = {"Distance": label}
        for acc in accounts:
            acc_lbl = account_labels.get(acc["email"], acc["email"])
            acc_df = df_all[df_all["garmin_account"] == acc["email"]]
            best = best_activity_for_distance(acc_df, low, high)
            if best:
                t_s = int(best["duration_min"] * 60 * dist_km / best["distance_km"])
                row[acc_lbl] = format_duration_hms(t_s)
            else:
                row[acc_lbl] = "—"
        comp_rows.append(row)

    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
