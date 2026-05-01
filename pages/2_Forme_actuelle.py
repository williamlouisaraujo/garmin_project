from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.auth import require_password
from src.garmin_client import (
    get_lactate_threshold_data,
    get_training_readiness_data,
    get_user_profile_data,
    get_vo2max_data,
)
from src.storage import get_accounts, get_activities_df
from src.transform import format_pace

st.set_page_config(page_title="Forme actuelle", page_icon="💪", layout="wide")
require_password()

st.title("💪 Forme actuelle")

# ── Sélection du compte ───────────────────────────────────────────────────────
try:
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Supabase inaccessible : {exc}")
    st.stop()

if not accounts:
    st.warning("Aucun compte Garmin configuré. Ajoutez-en un depuis la page Connexion.")
    st.stop()

if len(accounts) > 1:
    account_labels = {a["email"]: a.get("label", a["email"]) for a in accounts}
    choix = st.selectbox("Compte", list(account_labels.values()))
    selected = next(a for a in accounts if a.get("label", a["email"]) == choix)
else:
    selected = accounts[0]

email, password = selected["email"], selected["password"]
today = date.today().isoformat()

# ── Chargement données Garmin ─────────────────────────────────────────────────
with st.spinner("Récupération des données Garmin Connect…"):
    vo2max_raw = get_vo2max_data(email, password, today)
    lt_raw = get_lactate_threshold_data(email, password)
    profile_raw = get_user_profile_data(email, password)
    readiness_raw = get_training_readiness_data(email, password, today)
    df_act = get_activities_df(garmin_account=email)


# ── Parseurs robustes ─────────────────────────────────────────────────────────

def _extract_vo2max(data) -> float | None:
    if not data:
        return None
    if isinstance(data, list):
        for item in data:
            for k in ("vo2MaxPreciseValue", "vo2MaxValue", "value"):
                if item.get(k):
                    return float(item[k])
    if isinstance(data, dict):
        # Format metricsMap
        metrics = data.get("allMetrics", {}).get("metricsMap", {})
        for key in ("METRIC_VO2_MAX_RUNNING", "METRIC_VO2_MAX"):
            vals = metrics.get(key, [])
            if vals:
                v = vals[-1].get("value")
                if v:
                    return float(v)
        for k in ("vo2MaxPreciseValue", "vo2MaxValue"):
            if data.get(k):
                return float(data[k])
    return None


def _extract_lt(data) -> tuple[int | None, float | None]:
    """Retourne (FC_seuil, allure_seuil_min_km)."""
    if not data:
        return None, None
    item = data[0] if isinstance(data, list) and data else data
    if not isinstance(item, dict):
        return None, None
    hr = item.get("lactateThresholdHeartRate") or item.get("heartRate")
    speed = item.get("lactateThresholdSpeed") or item.get("speed")
    pace = round(1000 / (float(speed) * 60), 3) if speed and float(speed) > 0 else None
    return (int(hr) if hr else None), pace


def _extract_fcmax(data) -> int | None:
    if not data:
        return None
    for k in ("maxHrpm", "maxHeartRate", "max_heart_rate"):
        if data.get(k):
            return int(data[k])
    return None


def _extract_readiness(data) -> int | None:
    if not data:
        return None
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        for k in ("score", "trainingReadinessScore", "value"):
            if data.get(k) is not None:
                return int(data[k])
    return None


# ── Calculs ───────────────────────────────────────────────────────────────────

vo2max = _extract_vo2max(vo2max_raw)
lt_hr, lt_pace = _extract_lt(lt_raw)
fcmax_garmin = _extract_fcmax(profile_raw)
readiness = _extract_readiness(readiness_raw)

# FCmax : Garmin > max activités > Tanaka (208 - 0.7 * âge)
fcmax_activities = int(df_act["max_hr"].dropna().max()) if not df_act.empty and "max_hr" in df_act.columns and df_act["max_hr"].notna().any() else None
fcmax = fcmax_garmin or fcmax_activities

# VMA depuis VO2max (formule ACSM : VO2 = 3.5 + 0.2*S, S en m/min)
if vo2max and vo2max > 0:
    vma_mpm = (vo2max - 3.5) / 0.2
    vma_kmh = round(vma_mpm * 60 / 1000, 1)
    vma_pace_min_km = round(60.0 / vma_kmh, 3)  # pace à VMA
    vma_source = "Garmin VO2max"
else:
    vma_kmh = None
    vma_pace_min_km = None
    vma_source = "—"

# Seuil lactique estimé si pas natif
lt_hr_estimated = round(fcmax * 0.865) if fcmax and not lt_hr else lt_hr
lt_pace_estimated = round(vma_pace_min_km / 0.865, 3) if vma_pace_min_km and not lt_pace else lt_pace

# ── Section 1 : Métriques clés ────────────────────────────────────────────────
st.subheader("Métriques clés")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    if vo2max:
        st.metric("VO2max", f"{vo2max:.1f} ml/kg/min", help="Source : Garmin Connect natif")
    else:
        st.metric("VO2max", "—", help="Non disponible — nécessite une montre Garmin compatible")

with c2:
    if vma_kmh:
        st.metric("VMA", f"{vma_kmh} km/h", help=f"{format_pace(vma_pace_min_km)} /km — calculée depuis VO2max (ACSM)")
    else:
        st.metric("VMA", "—")

with c3:
    if fcmax:
        src = "Garmin" if fcmax_garmin else "max activités"
        st.metric("FC max", f"{fcmax} bpm", help=f"Source : {src}")
    else:
        st.metric("FC max", "—")

with c4:
    if lt_hr_estimated:
        src_lt = "Garmin natif" if lt_hr else "estimé (86.5% FCmax)"
        st.metric("FC seuil lactique", f"{lt_hr_estimated} bpm", help=f"Source : {src_lt}")
    else:
        st.metric("FC seuil lactique", "—")

with c5:
    if readiness is not None:
        color = "🟢" if readiness >= 70 else ("🟡" if readiness >= 40 else "🔴")
        st.metric("Forme du jour", f"{color} {readiness}/100", help="Training Readiness Garmin")
    else:
        st.metric("Forme du jour", "—")

st.divider()

# ── Section 2 : Zones d'entraînement ─────────────────────────────────────────
st.subheader("Zones d'entraînement")

ZONES = [
    ("Zone 1", "Récupération active",       0.55, 0.65,   0.50, 0.60, "#4CAF50"),
    ("Zone 2", "Endurance fondamentale",    0.65, 0.75,   0.60, 0.70, "#8BC34A"),
    ("Zone 3", "Aérobie — allure marathon", 0.75, 0.85,   0.70, 0.80, "#FFC107"),
    ("Zone 4", "Seuil lactique — tempo",    0.85, 0.92,   0.80, 0.90, "#FF9800"),
    ("Zone 5", "VO2max — fractionné",       0.95, 1.05,   0.90, 1.00, "#F44336"),
]

rows = []
for zone_name, desc, vma_lo, vma_hi, fc_lo, fc_hi, _ in ZONES:
    pace_lo = format_pace(vma_pace_min_km / vma_hi) if vma_pace_min_km else "—"
    pace_hi = format_pace(vma_pace_min_km / vma_lo) if vma_pace_min_km else "—"
    allure = f"{pace_lo} → {pace_hi}" if vma_pace_min_km else "—"

    fc_lo_val = round(fcmax * fc_lo) if fcmax else None
    fc_hi_val = round(fcmax * fc_hi) if fcmax else None
    fc_range = f"{fc_lo_val} → {fc_hi_val} bpm" if fcmax else "—"

    rows.append({
        "Zone": zone_name,
        "Description": desc,
        "% VMA": f"{int(vma_lo*100)}–{int(vma_hi*100)}%",
        "Allure cible": allure,
        "% FCmax": f"{int(fc_lo*100)}–{int(fc_hi*100)}%",
        "FC cible": fc_range,
    })

df_zones = pd.DataFrame(rows)
st.dataframe(df_zones, use_container_width=True, hide_index=True)

if not vma_kmh and not fcmax:
    st.caption("⚠️ Aucune donnée VMA ou FCmax disponible. Synchronisez d'abord vos activités et assurez-vous que votre montre mesure la FC et le VO2max.")

st.divider()

# ── Section 3 : Seuil lactique ────────────────────────────────────────────────
st.subheader("Seuil lactique")

lt_col1, lt_col2, lt_col3 = st.columns(3)

with lt_col1:
    if lt_hr:
        st.metric("FC au seuil", f"{lt_hr} bpm", help="Source : Garmin Connect natif")
    elif lt_hr_estimated:
        st.metric("FC au seuil (estimée)", f"{lt_hr_estimated} bpm", help="Estimé : 86.5% FCmax")
    else:
        st.metric("FC au seuil", "—")

with lt_col2:
    if lt_pace:
        st.metric("Allure au seuil", format_pace(lt_pace), help="Source : Garmin Connect natif")
    elif lt_pace_estimated:
        st.metric("Allure au seuil (estimée)", format_pace(lt_pace_estimated), help="Estimé : allure à 86.5% VMA")
    else:
        st.metric("Allure au seuil", "—")

with lt_col3:
    native_source = lt_hr is not None
    st.metric("Source", "Garmin natif ✅" if native_source else "Calculé ⚙️")

if not native_source:
    st.caption(
        "Le seuil lactique natif n'est pas disponible. Pour l'obtenir, effectuez un test de seuil "
        "lactique guidé depuis votre montre Garmin (activité > Tests > Seuil lactique)."
    )

st.divider()

# ── Section 4 : Données brutes (debug) ───────────────────────────────────────
with st.expander("🔍 Données brutes Garmin (diagnostic)", expanded=False):
    st.json({
        "vo2max_raw": vo2max_raw,
        "lactate_threshold_raw": lt_raw,
        "user_profile_raw": profile_raw,
        "training_readiness_raw": readiness_raw,
    })
    st.caption("Ces données sont retournées directement par l'API Garmin Connect.")
