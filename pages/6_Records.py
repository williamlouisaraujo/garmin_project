from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from src.garmin_client import (
    get_personal_records_native,
    get_race_predictions_native,
)
from src.storage import (
    get_accounts,
    get_activities_df,
    get_strava_account_for_garmin,
    get_strava_records_from_view,
)
from src.transform import format_duration_hms, format_pace

st.title("🏆 Records & Prédictions")

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

_GARMIN_PR_TYPE_IDS: dict[int, float] = {
    1:  1.0,
    2:  1.60934,
    3:  5.0,
    4:  10.0,
    5:  21.0975,
    6:  42.195,
    7:  50.0,
    8:  100.0,
}

_GARMIN_PRED_KEYS: dict[str, float] = {
    "time5K":           5.0,
    "time10K":          10.0,
    "timeHalfMarathon": 21.0975,
    "timeMarathon":     42.195,
}


def riegel(t1_s: float, d1_km: float, d2_km: float) -> int:
    return int(t1_s * (d2_km / d1_km) ** 1.06)


def _fit_loglog_linear(anchor_times: dict[float, int]) -> tuple[float, float] | None:
    if len(anchor_times) < 2:
        return None
    xs = [math.log(d) for d, t in anchor_times.items() if d > 0 and t > 0]
    ys = [math.log(t) for d, t in anchor_times.items() if d > 0 and t > 0]
    n = len(xs)
    if n < 2:
        return None
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    var_x = sum((x - x_mean) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    b = cov_xy / var_x
    a = y_mean - b * x_mean
    return a, b


def _build_hybrid_predictor(
    garmin_predictions: dict[float, int],
    fallback_ref: tuple[float, float] | None = None,
):
    anchors = {d: int(t) for d, t in garmin_predictions.items() if d > 0 and t > 0}
    if len(anchors) >= 2:
        d_sorted = sorted(anchors.keys())

        def predict(dist_km: float) -> int | None:
            if dist_km <= 0:
                return None
            if dist_km in anchors:
                return anchors[dist_km]
            if dist_km < d_sorted[0]:
                d1, d2 = d_sorted[0], d_sorted[1]
                e = math.log(anchors[d2] / anchors[d1]) / math.log(d2 / d1)
                return int(round(anchors[d1] * (dist_km / d1) ** e))
            if dist_km > d_sorted[-1]:
                d1, d2 = d_sorted[-2], d_sorted[-1]
                e = math.log(anchors[d2] / anchors[d1]) / math.log(d2 / d1)
                return int(round(anchors[d2] * (dist_km / d2) ** e))
            for left, right in zip(d_sorted[:-1], d_sorted[1:]):
                if left <= dist_km <= right:
                    e = math.log(anchors[right] / anchors[left]) / math.log(right / left)
                    return int(round(anchors[left] * (dist_km / left) ** e))
            return None

        return predict

    fit = _fit_loglog_linear(anchors)
    if fit:
        a, b = fit

        def predict_reg(dist_km: float) -> int | None:
            if dist_km <= 0:
                return None
            return int(round(math.exp(a + b * math.log(dist_km))))

        return predict_reg

    if fallback_ref is not None:
        d_ref, t_ref = fallback_ref

        def predict_riegel(dist_km: float) -> int | None:
            if dist_km <= 0:
                return None
            return riegel(t_ref, d_ref, dist_km)

        return predict_riegel

    return lambda _dist_km: None


def best_activity_for_distance(df: pd.DataFrame, low_km: float, high_km: float) -> dict | None:
    mask = (df["distance_km"] >= low_km) & (df["distance_km"] <= high_km) & (df["duration_min"] > 0)
    candidates = df[mask].copy()
    if candidates.empty:
        return None
    candidates["pace"] = candidates["duration_min"] / candidates["distance_km"]
    return candidates.loc[candidates["pace"].idxmin()].to_dict()


def _parse_pr_time_s(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_garmin_prs(raw) -> dict[float, dict]:
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


# ── Chargement des comptes (nécessaire pour les deux sources) ─────────────────
try:
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Supabase inaccessible : {exc}")
    st.stop()

if not accounts:
    st.info("Aucun compte configuré. Synchronisez depuis la page Connexion.")
    st.stop()

account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}

# ── Filtre utilisateur (commun aux deux sources) ──────────────────────────────
if len(accounts) > 1:
    choix = st.selectbox("Utilisateur", list(account_labels.values()))
    selected_acc = next(a for a in accounts if a.get("label", a["email"]) == choix)
else:
    selected_acc = accounts[0]

# ── Filtre source ─────────────────────────────────────────────────────────────
source_filter = st.radio(
    "Source",
    ["Garmin", "Strava"],
    horizontal=True,
    key="records_source",
)

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# Branche STRAVA
# ═════════════════════════════════════════════════════════════════════════════
if source_filter == "Strava":
    garmin_email = selected_acc["email"]
    garmin_label = selected_acc.get("label", garmin_email)
    st.caption(f"Records Strava de **{garmin_label}** (depuis Supabase — sync depuis la page Synchronisation).")

    strava_acc = get_strava_account_for_garmin(garmin_email)
    if not strava_acc or not strava_acc.get("access_token"):
        st.info(
            f"ℹ️ Le compte Strava de **{garmin_label}** n'est pas connecté. "
            "Allez dans **Synchronisation** et cliquez sur **🔗 Connecter Strava** "
            f"en face de {garmin_label}."
        )
        st.stop()

    strava_records = get_strava_records_from_view(garmin_email)
    if strava_records is None:
        st.info(
            f"ℹ️ Aucun record Strava disponible pour **{garmin_label}**. "
            "Allez dans **Synchronisation** et cliquez sur **🔄 Sync Strava** "
            "pour importer vos activités et best_efforts."
        )
        st.stop()

    rows = []
    for label, dist_km, _low, _high in TARGETS:
        record = strava_records.get(dist_km)
        if record:
            t_s = int(record["time_s"])
            rows.append({
                "Distance": label,
                "Record": format_duration_hms(t_s),
                "Allure": format_pace(t_s / 60 / dist_km),
                "Date": record.get("date", "—"),
                "Activité": record.get("activity_name", "—"),
                "Source": "Strava ✅",
            })
        else:
            rows.append({
                "Distance": label,
                "Record": "—",
                "Allure": "—",
                "Date": "—",
                "Activité": "—",
                "Source": "—",
            })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    missing = [lbl for lbl, dist_km, *_ in TARGETS if dist_km not in strava_records]
    if missing:
        st.caption(
            f"ℹ️ Distances sans record Strava : {', '.join(missing)}. "
            "Strava ne propose pas de best_efforts pour ces distances "
            "(500 m, 30 km, 100 km), ou elles n'ont pas encore été réalisées."
        )

    with st.expander("🔍 Données brutes Strava (diagnostic)", expanded=False):
        st.json({str(k): v for k, v in strava_records.items()})

    st.stop()

# ═════════════════════════════════════════════════════════════════════════════
# Branche GARMIN (comportement existant, inchangé)
# ═════════════════════════════════════════════════════════════════════════════
st.caption("Records personnels et prédictions de course issus de Garmin Connect.")

try:
    df_all = get_activities_df()
except Exception as exc:
    st.error(f"❌ Supabase inaccessible : {exc}")
    st.stop()

if df_all.empty:
    st.info("Aucune activité. Synchronisez depuis la page Connexion.")
    st.stop()

df_all["start_time"] = pd.to_datetime(df_all["start_time"])
selected_df = df_all[df_all["garmin_account"] == selected_acc["email"]] if "garmin_account" in df_all.columns else df_all

# ── Récupération données natives Garmin ───────────────────────────────────────
garmin_prs: dict[float, dict] = {}
garmin_preds: dict[float, int] = {}
pr_raw = None
pred_raw = None

with st.spinner("Récupération des records et prédictions Garmin…"):
    pr_raw = get_personal_records_native(selected_acc["email"], selected_acc["password"])
    pred_raw = get_race_predictions_native(selected_acc["email"], selected_acc["password"])
garmin_prs = _parse_garmin_prs(pr_raw)
garmin_preds = _parse_garmin_predictions(pred_raw)

# ── Référence pour Riegel (fallback) ─────────────────────────────────────────
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

# ── Construction du prédicteur hybride ───────────────────────────────────────
predict_time_s = _build_hybrid_predictor(
    garmin_predictions=garmin_preds,
    fallback_ref=(ref_dist_km, ref_time_s) if (ref_dist_km and ref_time_s) else None,
)

# ── Tableau records + prédictions ────────────────────────────────────────────
rows = []
for label, dist_km, low, high in TARGETS:
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

    garmin_pred_s = garmin_preds.get(dist_km)
    if garmin_pred_s:
        pred_str = format_duration_hms(garmin_pred_s)
        pred_pace = format_pace(garmin_pred_s / 60 / dist_km)
        pred_source = "Garmin ✅"
    else:
        model_s = predict_time_s(dist_km)
        if model_s:
            pred_str = format_duration_hms(model_s)
            pred_pace = format_pace(model_s / 60 / dist_km)
            pred_source = "Modèle calibré ⚙️" if garmin_preds else "Riegel ⚙️"
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
if garmin_preds:
    st.caption("ℹ️ Les distances sans prédiction Garmin sont estimées via un modèle hybride calibré sur 5k/10k/semi/marathon.")
elif not garmin_preds:
    st.caption("ℹ️ Aucune prédiction Garmin native disponible — prédictions calculées via formule de Riegel.")

with st.expander("🔍 Données brutes Garmin (diagnostic)", expanded=False):
    st.write("**Records natifs**")
    st.json(pr_raw)
    st.write("**Prédictions natives**")
    st.json(pred_raw)
