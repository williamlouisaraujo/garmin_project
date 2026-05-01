from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.auth import require_password
from src.garmin_client import get_vo2max_data
from src.storage import get_accounts
from src.tcx_writer import generate_tcx
from src.training_plan import Session, _race_pct_vma, generate_plan
from src.transform import format_pace

st.set_page_config(page_title="Programme", page_icon="📅", layout="wide")
require_password()

st.title("📅 Programme d'entraînement")
st.caption("Configurez un objectif et obtenez un plan basé sur votre VMA avec séances téléchargeables.")

# ── Chargement comptes ────────────────────────────────────────────────────────
try:
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Supabase inaccessible : {exc}")
    st.stop()

# ── Formulaire ────────────────────────────────────────────────────────────────
with st.form("objectif"):
    st.subheader("Objectif de course")
    col1, col2 = st.columns(2)

    with col1:
        goal_date = st.date_input(
            "Date de la course",
            value=date.today() + timedelta(weeks=12),
            min_value=date.today() + timedelta(weeks=4),
        )
        goal_distance = st.number_input(
            "Distance (km)", min_value=0.5, max_value=200.0, value=10.0, step=0.5,
        )
        st.markdown("**Temps objectif**")
        tc1, tc2, tc3 = st.columns(3)
        t_h = tc1.number_input("h",   min_value=0, max_value=24, value=0, step=1)
        t_m = tc2.number_input("min", min_value=0, max_value=59, value=50, step=1)
        t_s = tc3.number_input("s",   min_value=0, max_value=59, value=0,  step=1)

    with col2:
        st.markdown("**VMA (Vitesse Maximale Aérobie)**")
        vma_mode = st.radio(
            "Source VMA",
            ["Saisie manuelle", "Récupérer depuis Garmin Connect"],
            horizontal=True,
        )
        if vma_mode == "Saisie manuelle":
            vma_input = st.number_input(
                "VMA (km/h)", min_value=6.0, max_value=28.0, value=14.0, step=0.5,
                help="Si vous ne connaissez pas votre VMA, laissez 0 et le plan utilisera l'allure objectif.",
            )
        else:
            vma_input = None
            if accounts:
                acc_labels = [a.get("label", a["email"]) for a in accounts]
                vma_account_label = st.selectbox("Compte pour récupérer la VMA", acc_labels)
            else:
                st.warning("Aucun compte Garmin configuré.")
                vma_account_label = None

    submitted = st.form_submit_button("🗓️ Générer le programme", use_container_width=True)

# ── Calcul VMA si mode Garmin ─────────────────────────────────────────────────
if not submitted and "plan" not in st.session_state:
    st.info("Remplissez le formulaire ci-dessus et cliquez sur **Générer le programme**.")
    st.stop()

if submitted:
    goal_time_min = t_h * 60 + t_m + t_s / 60 if (t_h + t_m + t_s) > 0 else None
    goal_pace = goal_time_min / goal_distance if goal_time_min else None

    # Récupération VMA
    vma_kmh: float | None = None
    vma_source = "non renseignée"

    if vma_mode == "Saisie manuelle" and vma_input and vma_input > 0:
        vma_kmh = vma_input
        vma_source = f"saisie manuelle ({vma_kmh} km/h)"
    elif vma_mode == "Récupérer depuis Garmin Connect" and accounts and vma_account_label:
        acc = next((a for a in accounts if a.get("label", a["email"]) == vma_account_label), None)
        if acc:
            with st.spinner("Récupération VO2max Garmin…"):
                raw = get_vo2max_data(acc["email"], acc["password"])
            vo2max = None
            if raw:
                if isinstance(raw, list):
                    for it in raw:
                        for k in ("vo2MaxPreciseValue", "vo2MaxValue", "value"):
                            if it.get(k):
                                vo2max = float(it[k]); break
                elif isinstance(raw, dict):
                    mm = raw.get("allMetrics", {}).get("metricsMap", {})
                    for key in ("METRIC_VO2_MAX_RUNNING", "METRIC_VO2_MAX"):
                        vals = mm.get(key, [])
                        if vals:
                            vo2max = float(vals[-1].get("value", 0) or 0); break
                    if not vo2max:
                        for k in ("vo2MaxPreciseValue", "vo2MaxValue"):
                            if raw.get(k):
                                vo2max = float(raw[k]); break
            if vo2max and vo2max > 0:
                vma_mpm = (vo2max - 3.5) / 0.2
                vma_kmh = round(vma_mpm * 60 / 1000, 1)
                vma_source = f"Garmin VO2max={vo2max:.1f} → VMA={vma_kmh} km/h"
                st.success(f"✅ VO2max récupéré : {vo2max:.1f} ml/kg/min → VMA = {vma_kmh} km/h")
            else:
                st.warning("VO2max non disponible depuis Garmin. Le plan utilisera l'allure objectif.")

    st.session_state["plan"] = generate_plan(
        goal_date=goal_date,
        goal_distance_km=goal_distance,
        goal_time_min=goal_time_min,
        goal_pace_min_km=goal_pace,
        vma_kmh=vma_kmh,
    )
    st.session_state["plan_meta"] = {
        "goal_date": goal_date,
        "goal_distance": goal_distance,
        "goal_time_min": goal_time_min,
        "goal_pace": goal_pace,
        "vma_kmh": vma_kmh,
        "vma_source": vma_source,
    }

plan = st.session_state.get("plan", [])
meta = st.session_state.get("plan_meta", {})
if not plan:
    st.stop()

# ── Résumé ────────────────────────────────────────────────────────────────────
st.divider()
weeks_until = len(plan) - 1
meta_vma = meta.get("vma_kmh")
meta_gt  = meta.get("goal_time_min")

col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
col_r1.metric("Semaines de prépa", weeks_until)
col_r2.metric("Distance objectif", f"{meta.get('goal_distance', '—')} km")
if meta_gt:
    h = int(meta_gt // 60); m = int(meta_gt % 60)
    col_r3.metric("Temps objectif", f"{h}h{m:02d}min")
if meta.get("goal_pace"):
    col_r4.metric("Allure objectif", format_pace(meta["goal_pace"]))
if meta_vma:
    col_r5.metric("VMA utilisée", f"{meta_vma} km/h")

if meta_vma and meta_gt:
    pct = _race_pct_vma(meta_gt)
    st.caption(
        f"Allure course calculée à **{round(pct*100)}% de la VMA** "
        f"pour une course de {meta_gt:.0f}min — source : {meta.get('vma_source', '—')}"
    )
elif not meta_vma:
    st.caption("⚠️ VMA non renseignée — allures dérivées de l'allure objectif. Renseignez votre VMA pour un plan plus précis.")

# ── Calendrier ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Calendrier d'entraînement")

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

for week in plan:
    phase = week["phase"]
    week_label = (
        f"**S{week['week_num']}** — {phase}  "
        f"| {week['week_start'].strftime('%d/%m')} → {week['week_end'].strftime('%d/%m/%Y')}  "
        f"| ~{week['total_km']} km"
    )

    with st.expander(week_label, expanded=(phase == "Course")):
        sessions: list[Session] = week["sessions"]
        cols = st.columns(7)
        for day_idx, col in enumerate(cols):
            with col:
                sess = next((s for s in sessions if s.day == day_idx), None)
                if sess is None or sess.type == "REST":
                    st.markdown(f"**{JOURS[day_idx]}**")
                    st.caption("Repos")
                else:
                    st.markdown(f"**{JOURS[day_idx]} {sess.date.strftime('%d/%m')}**")
                    st.markdown(sess.name)
                    if sess.duration_min:
                        st.caption(f"{sess.duration_min:.0f}min")
                    if sess.distance_km:
                        st.caption(f"~{sess.distance_km:.1f}km")

        st.divider()
        for sess in sessions:
            if sess.type == "REST":
                continue
            col_info, col_dl = st.columns([5, 1])
            with col_info:
                st.markdown(f"**{JOURS[sess.day]} {sess.date.strftime('%d/%m')}** — {sess.name}")
                st.caption(sess.description)
            with col_dl:
                if sess.tcx_steps:
                    tcx = generate_tcx(name=sess.name, steps=sess.tcx_steps, notes=sess.description)
                    st.download_button(
                        label="📥 TCX",
                        data=tcx.encode("utf-8"),
                        file_name=f"{sess.date.isoformat()}_{sess.type}.tcx",
                        mime="application/xml",
                        key=f"dl_{week['week_num']}_{sess.day}",
                        help="Télécharger et importer dans Garmin Connect",
                    )

st.divider()
st.info(
    "**Import TCX dans Garmin Connect** : téléchargez le fichier → "
    "Garmin Connect web → *Entraînements* → *Importer* → sélectionnez le .tcx. "
    "La séance apparaît dans votre bibliothèque et peut être envoyée à la montre."
)
