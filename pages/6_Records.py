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

# Mapping types Garmin PR → distance km
_GARMIN_PR_DIST: dict[str, float] = {
    # Standard type IDs
    "fastest_5K": 5.0, "Best5K": 5.0,
    "fastest_10K": 10.0, "Best10K": 10.0,
    "fastest_half_marathon": 21.0975, "BestHalfMarathon": 21.0975,
    "fastest_marathon": 42.195, "BestMarathon": 42.195,
    "fastest_mile": 1.60934, "BestMile": 1.60934,
    "fastest_1K": 1.0, "Best1K": 1.0,
    "fastest_400m": 0.4, "Best400m": 0.4,
    # Garmin may use camelCase or snake_case
    "fastestMile": 1.60934,
    "fastest5k": 5.0,
    "fastest10k": 10.0,
    "fastestHalfMarathon": 21.0975,
    "fastestMarathon": 42.195,
    "fastest_500m": 0.5,
    "Best500m": 0.5,
    "fastest_30K": 30.0,
    "Best30K": 30.0,
    "fastest_50K": 50.0,
    "Best50K": 50.0,
    "fastest_100K": 100.0,
    "Best100K": 100.0,
}

# Mapping prédictions Garmin → distance km
_GARMIN_PRED_DIST: dict[str, float] = {
    "5K": 5.0, "5k": 5.0, "5Km": 5.0,
    "10K": 10.0, "10k": 10.0, "10Km": 10.0,
    "halfMarathon": 21.0975, "HalfMarathon": 21.0975, "half_marathon": 21.0975,
    "marathon": 42.195, "Marathon": 42.195,
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
    """Extrait les PRs Garmin et les mappe sur une distance en km."""
    result: dict[float, dict] = {}
    if not raw:
        return result
    # Garmin peut retourner une liste ou un dict {sport: [items]}
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
        type_id = item.get("typeId") or item.get("type") or ""
        dist = _GARMIN_PR_DIST.get(type_id)
        if dist is None:
            continue
        # La valeur peut être en secondes, ms, ou autre
        raw_val = item.get("value") or item.get("time") or item.get("duration")
        t_s = _parse_pr_time_s(raw_val)
        if t_s is None:
            continue
        # Garmin stocke parfois en ms (> 100000 pour un 5km semble anormal)
        if t_s > 10_000 and dist <= 5.0:
            t_s /= 1000.0
        date_str = item.get("prDate") or item.get("pr_date") or item.get("date") or ""
        if dist not in result or t_s < result[dist]["time_s"]:
            result[dist] = {"time_s": t_s, "date": date_str}
    return result


def _parse_garmin_predictions(raw) -> dict[float, int]:
    """Extrait les prédictions Garmin en {distance_km: seconds}."""
    result: dict[float, int] = {}
    if not raw:
        return result
    # Peut être {event: seconds} ou {"racePredictions": {...}}
    container = raw
    if isinstance(raw, dict):
        container = raw.get("racePredictions") or raw
    if isinstance(container, dict):
        for k, v in container.items():
            dist = _GARMIN_PRED_DIST.get(k)
            if dist is None:
                continue
            # v peut être un float (secondes), un dict, ou autre
            if isinstance(v, (int, float)) and v > 0:
                result[dist] = int(v)
            elif isinstance(v, dict):
                t = v.get("timePrediction") or v.get("time") or v.get("value")
                if t and float(t) > 0:
                    result[dist] = int(float(t))
    elif isinstance(container, list):
        for item in container:
            if not isinstance(item, dict):
                continue
            event = item.get("event") or item.get("type") or ""
            dist = _GARMIN_PRED_DIST.get(event)
            if dist is None:
                continue
            t = item.get("timePrediction") or item.get("time") or item.get("value")
            if t and float(t) > 0:
                result[dist] = int(float(t))
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

if selected_acc:
    with st.spinner("Récupération des records et prédictions Garmin…"):
        pr_raw = get_personal_records_native(selected_acc["email"], selected_acc["password"])
        pred_raw = get_race_predictions_native(selected_acc["email"], selected_acc["password"])
    garmin_prs = _parse_garmin_prs(pr_raw)
    garmin_preds = _parse_garmin_predictions(pred_raw)
elif accounts:
    with st.spinner("Agrégation des records Garmin multi-comptes…"):
        for acc in accounts:
            pr_raw = get_personal_records_native(acc["email"], acc["password"])
            pred_raw = get_race_predictions_native(acc["email"], acc["password"])
            for dist, rec in _parse_garmin_prs(pr_raw).items():
                if dist not in garmin_prs or rec["time_s"] < garmin_prs[dist]["time_s"]:
                    garmin_prs[dist] = rec
            for dist, pred in _parse_garmin_predictions(pred_raw).items():
                if dist not in garmin_preds or pred < garmin_preds[dist]:
                    garmin_preds[dist] = pred

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