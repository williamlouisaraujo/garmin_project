from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import require_password
from src.garmin_client import (
    get_personal_records_native,
    get_race_predictions_native,
)
from src.storage import get_accounts, get_activities_df
from src.transform import format_duration_hms, format_pace

st.set_page_config(page_title="Records", page_icon="🏆", layout="wide")
require_password()

st.title("🏆 Records & Prédictions")
st.caption("Records personnels et prédictions de course issus de Garmin Connect.")

# ── Distances cibles ──────────────────────────────────────────────────────────
TARGETS: list[tuple[str, float, float, float]] = [
    ("500 m",         0.5,     0.40,  0.60),
    ("1 km",          1.0,     0.90,  1.10),
    ("5 km",          5.0,     4.70,  5.30),
    ("10 km",        10.0,     9.50, 10.50),
    ("Semi-marathon", 21.0975, 20.0,  22.5),
    ("30 km",        30.0,    28.0,  32.0),
    ("Marathon",     42.195,  41.0,  43.5),
    ("50 km",        50.0,    47.0,  53.0),
    ("100 km",      100.0,    95.0, 105.0),
]

# Mapping typeId (int) Garmin PR → distance_km
# Dérivé de l'observation réelle : typeId 5 → semi (5860s = 1:37:40)
_GARMIN_PR_TYPE_IDS: dict[int, float] = {
    1:  1.0,      # Fastest 1 km
    2:  1.60934,  # Fastest 1 mile
    3:  5.0,      # Fastest 5 km
    4:  10.0,     # Fastest 10 km
    5:  21.0975,  # Fastest half marathon
    6:  42.195,   # Fastest marathon
    7:  50.0,     # Fastest 50 km
    8:  100.0,    # Fastest 100 km
    # typeIds 12-16 = records non temporels (longest distance, elevation, etc.)
}

# Mapping clés prédictions Garmin → distance_km (format réel observé)
_GARMIN_PRED_KEYS: dict[str, float] = {
    "time5K":           5.0,
    "time10K":          10.0,
    "timeHalfMarathon": 21.0975,
    "timeMarathon":     42.195,
}


def riegel(t1_s: float, d1_km: float, d2_km: float) -> int:
    return int(t1_s * (d2_km / d1_km) ** 1.06)


def best_activity_for_distance(df: pd.DataFrame, low_km: float, high_km: float) -> dict | None:
    mask = (df["distance_km"] >= low_km) & (df["distance_km"] <= high_km) & (df["duration_min"] > 0)
    candidates = df[mask].copy()
    if candidates.empty:
        return None
    candidates["pace"] = candidates["duration_min"] / candidates["distance_km"]
    return candidates.loc[candidates["pace"].idxmin()].to_dict()


def _parse_pr_time_s(value) -> float | None:
    """Essaie d'interpréter la valeur Garmin comme des secondes."""
    if value is None:
        return None
    try:
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_garmin_prs(raw) -> dict[float, dict]:
    """Extrait les PRs Garmin et les mappe sur une distance en km.

    Format réel observé : liste de dicts avec typeId (int), value (secondes),
    prStartTimeGmtFormatted (date).
    """
    result: dict[float, dict] = {}
    if not raw:
        return result
    items: list = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for v in raw.values():
            if isinstance(v, list):
                items.extend(v)
    for item in items:
        if not isinstance(item, dict):
            continue
        type_id = item.get("typeId")
        try:
            type_id = int(type_id)
        except (TypeError, ValueError):
            continue
        dist = _GARMIN_PR_TYPE_IDS.get(type_id)
        if dist is None:
            continue
        raw_val = item.get("value") or item.get("time") or item.get("duration")
        t_s = _parse_pr_time_s(raw_val)
        if t_s is None:
            continue
        date_str = (
            item.get("prStartTimeGmtFormatted")
            or item.get("prDate")
            or item.get("date")
            or "—"
        )
        if dist not in result or t_s < result[dist]["time_s"]:
            result[dist] = {"time_s": t_s, "date": date_str}
    return result


def _parse_garmin_predictions(raw) -> dict[float, int]:
    """Extrait les prédictions Garmin en {distance_km: seconds}.

    Format réel observé : dict plat avec clés time5K, time10K,
    timeHalfMarathon, timeMarathon (valeurs en secondes).
    """
    result: dict[float, int] = {}
    if not raw:
        return result
    container = raw if isinstance(raw, dict) else {}
    for k, dist in _GARMIN_PRED_KEYS.items():
        v = container.get(k)
        if v is None:
            continue
        try:
            t_s = float(v)
        except (TypeError, ValueError):
            continue
        if t_s > 0:
            result[dist] = int(t_s)
    return result


# ── Chargement ────────────────────────────────────────────────────────────────
try:
    accounts = get_accounts()
    df_all = get_activities_df()
except Exception as exc:
    st.error(f"❌ Supabase inaccessible : {exc}")
    st.stop()

if df_all.empty and not accounts:
    st.info("Aucune activité. Synchronisez depuis la page Connexion.")
    st.stop()

df_all["start_time"] = pd.to_datetime(df_all["start_time"])
account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}

# ── Filtre compte ─────────────────────────────────────────────────────────────
if len(accounts) > 1:
    options = ["Tous"] + list(account_labels.values())
    choix = st.selectbox("Utilisateur", options)
    if choix == "Tous":
        selected_acc = None
        selected_df = df_all
    else:
        selected_acc = next(a for a in accounts if a.get("label", a["email"]) == choix)
        selected_df = df_all[df_all["garmin_account"] == selected_acc["email"]]
else:
    selected_acc = accounts[0] if accounts else None
    selected_df = df_all

# ── Récupération données natives Garmin ───────────────────────────────────────
garmin_prs: dict[float, dict] = {}
garmin_preds: dict[float, int] = {}
pr_raw = None
pred_raw = None

if selected_acc:
    with st.spinner("Récupération des records et prédictions Garmin…"):
        pr_raw = get_personal_records_native(selected_acc["email"], selected_acc["password"])
        pred_raw = get_race_predictions_native(selected_acc["email"], selected_acc["password"])
    garmin_prs = _parse_garmin_prs(pr_raw)
    garmin_preds = _parse_garmin_predictions(pred_raw)

# ── Référence pour Riegel (fallback) ─────────────────────────────────────────
# Trouver le meilleur PR connu (Garmin ou activités) pour les prédictions Riegel
ref_dist_km, ref_time_s = None, None
for ref_prio in [5.0, 10.0, 21.0975, 42.195, 1.0]:
    if ref_prio in garmin_prs:
        ref_dist_km = ref_prio
        ref_time_s = garmin_prs[ref_prio]["time_s"]
        break
    best = best_activity_for_distance(selected_df, ref_prio * 0.94, ref_prio * 1.06)
    if best:
        ref_dist_km = ref_prio
        ref_time_s = int(best["duration_min"] * 60 * ref_prio / best["distance_km"])
        break

# ── Tableau records + prédictions ────────────────────────────────────────────
rows = []
for label, dist_km, low, high in TARGETS:
    # PR natif Garmin
    garmin_pr = garmin_prs.get(dist_km)
    if garmin_pr:
        pr_str = format_duration_hms(int(garmin_pr["time_s"]))
        pr_pace = format_pace(garmin_pr["time_s"] / 60 / dist_km)
        pr_date = garmin_pr.get("date", "—")
        pr_source = "Garmin ✅"
    else:
        best_act = best_activity_for_distance(selected_df, low, high)
        if best_act:
            t_s = int(best_act["duration_min"] * 60 * dist_km / best_act["distance_km"])
            pr_str = format_duration_hms(t_s)
            pr_pace = format_pace(t_s / 60 / dist_km)
            pr_date = pd.to_datetime(best_act["start_time"]).strftime("%d/%m/%Y") if best_act.get("start_time") else "—"
            pr_source = "Activités ⚙️"
        else:
            pr_str = pr_pace = pr_date = "—"
            pr_source = "—"

    # Prédiction natif Garmin
    garmin_pred_s = garmin_preds.get(dist_km)
    if garmin_pred_s:
        pred_str = format_duration_hms(garmin_pred_s)
        pred_pace = format_pace(garmin_pred_s / 60 / dist_km)
        pred_source = "Garmin ✅"
    elif ref_dist_km and ref_time_s:
        riegel_s = riegel(ref_time_s, ref_dist_km, dist_km)
        pred_str = format_duration_hms(riegel_s)
        pred_pace = format_pace(riegel_s / 60 / dist_km)
        pred_source = "Riegel ⚙️"
    else:
        pred_str = pred_pace = "—"
        pred_source = "—"

    rows.append({
        "Distance": label,
        "Record": pr_str,
        "Allure": pr_pace,
        "Date": pr_date,
        "Source PR": pr_source,
        "Prédiction": pred_str,
        "Allure préd.": pred_pace,
        "Source préd.": pred_source,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

if not garmin_prs:
    st.caption("ℹ️ Aucun record Garmin natif disponible — affichage des meilleures activités à distance équivalente.")
if not garmin_preds:
    st.caption("ℹ️ Aucune prédiction Garmin native disponible — prédictions calculées via formule de Riegel.")

# ── Données brutes debug ──────────────────────────────────────────────────────
with st.expander("🔍 Données brutes Garmin (diagnostic)", expanded=False):
    st.write("**Records natifs**")
    st.json(pr_raw)
    st.write("**Prédictions natives**")
    st.json(pred_raw)

# ── Comparaison multi-comptes ─────────────────────────────────────────────────
if len(accounts) > 1 and selected_acc is None:
    st.divider()
    st.subheader("Comparaison entre utilisateurs")
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
