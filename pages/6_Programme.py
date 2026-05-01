from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.auth import require_password
from src.tcx_writer import generate_tcx
from src.training_plan import Session, generate_plan
from src.transform import format_pace

st.set_page_config(page_title="Programme", page_icon="📅", layout="wide")
require_password()

st.title("📅 Programme d'entraînement")
st.caption("Configurez un objectif de course et obtenez un plan personnalisé avec séances téléchargeables.")

# ── Formulaire objectif ───────────────────────────────────────────────────────
with st.form("objectif"):
    st.subheader("Objectif")
    col1, col2, col3 = st.columns(3)

    with col1:
        goal_date = st.date_input(
            "Date de la course",
            value=date.today() + timedelta(weeks=12),
            min_value=date.today() + timedelta(weeks=4),
        )
        goal_distance = st.number_input(
            "Distance (km)", min_value=0.5, max_value=200.0, value=10.0, step=0.5,
        )

    with col2:
        st.markdown("**Objectif de temps** *(optionnel)*")
        col_h, col_m, col_s = st.columns(3)
        with col_h:
            t_h = st.number_input("h", min_value=0, max_value=24, value=0, step=1, label_visibility="visible")
        with col_m:
            t_m = st.number_input("min", min_value=0, max_value=59, value=50, step=1, label_visibility="visible")
        with col_s:
            t_s = st.number_input("s", min_value=0, max_value=59, value=0, step=1, label_visibility="visible")

    with col3:
        weekly_elev = st.number_input(
            "Dénivelé hebdomadaire habituel (m D+)",
            min_value=0, max_value=5000, value=0, step=50,
        )

    submitted = st.form_submit_button("🗓️ Générer le programme", use_container_width=True)

# ── Génération du plan ────────────────────────────────────────────────────────
if not submitted and "plan" not in st.session_state:
    st.info("Remplissez le formulaire ci-dessus et cliquez sur **Générer le programme**.")
    st.stop()

if submitted:
    goal_time_min = t_h * 60 + t_m + t_s / 60 if (t_h + t_m + t_s) > 0 else None
    goal_pace = goal_time_min / goal_distance if goal_time_min else None

    st.session_state["plan"] = generate_plan(
        goal_date=goal_date,
        goal_distance_km=goal_distance,
        goal_time_min=goal_time_min,
        goal_pace_min_km=goal_pace,
        weekly_elevation_m=weekly_elev,
    )
    st.session_state["plan_meta"] = {
        "goal_date": goal_date,
        "goal_distance": goal_distance,
        "goal_time_min": goal_time_min,
        "goal_pace": goal_pace,
    }

plan = st.session_state.get("plan", [])
meta = st.session_state.get("plan_meta", {})

if not plan:
    st.stop()

# ── Résumé ────────────────────────────────────────────────────────────────────
st.divider()
weeks_until = len(plan) - 1  # dernière semaine = course

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
col_r1.metric("Semaines de préparation", weeks_until)
col_r2.metric("Distance objectif", f"{meta.get('goal_distance', '—')} km")
if meta.get("goal_time_min"):
    h = int(meta["goal_time_min"] // 60)
    m = int(meta["goal_time_min"] % 60)
    col_r3.metric("Temps objectif", f"{h}h{m:02d}min")
if meta.get("goal_pace"):
    col_r4.metric("Allure objectif", format_pace(meta["goal_pace"]))

# ── Calendrier semaine par semaine ────────────────────────────────────────────
st.divider()
st.subheader("Calendrier d'entraînement")

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
PHASE_COLOR = {
    "Base": "#1e6e1e",
    "Construction": "#6e4c1e",
    "Pic": "#6e1e1e",
    "Affûtage": "#1e3c6e",
    "Course": "#5a1e6e",
}

for week in plan:
    phase = week["phase"]
    color = PHASE_COLOR.get(phase, "#333")
    week_label = (
        f"**Semaine {week['week_num']}** — {phase}  "
        f"| {week['week_start'].strftime('%d/%m')} → {week['week_end'].strftime('%d/%m/%Y')}  "
        f"| ~{week['total_km']} km"
    )

    with st.expander(week_label, expanded=(week["phase"] in ("Course",))):
        sessions: list[Session] = week["sessions"]
        # Grille 7 colonnes
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

        # Détail et téléchargement de chaque séance
        st.divider()
        for sess in sessions:
            if sess.type == "REST":
                continue
            with st.container():
                col_info, col_dl = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**{JOURS[sess.day]} {sess.date.strftime('%d/%m')}** — {sess.name}")
                    st.caption(sess.description)
                with col_dl:
                    if sess.tcx_steps:
                        tcx_content = generate_tcx(
                            name=sess.name,
                            steps=sess.tcx_steps,
                            notes=sess.description,
                        )
                        st.download_button(
                            label="📥 TCX",
                            data=tcx_content.encode("utf-8"),
                            file_name=f"{sess.date.isoformat()}_{sess.type}.tcx",
                            mime="application/xml",
                            key=f"dl_{week['week_num']}_{sess.day}",
                            help="Télécharger et importer dans Garmin Connect",
                        )

st.divider()
st.info(
    "**Import dans Garmin Connect** : téléchargez le fichier `.tcx` → "
    "Garmin Connect web → *Entraînements* → *Importer* → sélectionnez le fichier. "
    "La séance apparaît ensuite dans votre bibliothèque et peut être envoyée à votre montre."
)
