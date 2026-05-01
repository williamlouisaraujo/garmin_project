"""Algorithme de génération de plan d'entraînement course à pied."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


@dataclass
class Session:
    day: int                        # 0=lundi … 6=dimanche
    date: date
    type: str                       # EA, TE, IT, LO, RP, REST
    name: str
    description: str
    duration_min: Optional[float]
    distance_km: Optional[float]
    pace_target: Optional[float]    # allure principale en min/km
    pace_easy: Optional[float]      # allure footing en min/km
    tcx_steps: list[dict] = field(default_factory=list)


_EMOJI = {
    "EA": "🟢", "TE": "🟡", "IT": "🔴",
    "LO": "🔵", "RP": "🟠", "REST": "⚫",
}

_WARMUP_DURATION = 600    # 10 min échauffement (s)
_COOLDOWN_DURATION = 600  # 10 min retour au calme (s)


def _tcx_easy_run(duration_min: float, pace_easy: float) -> list[dict]:
    return [
        {"type": "step", "name": "Footing",
         "intensity": "active", "duration_type": "time",
         "duration_value": int(duration_min * 60),
         "target_type": "speed", "pace_low": pace_easy * 1.1, "pace_high": pace_easy * 0.95},
    ]


def _tcx_tempo(warmup_s: int, tempo_s: int, cooldown_s: int,
               pace_tempo: float, pace_easy: float) -> list[dict]:
    return [
        {"type": "step", "name": "Échauffement", "intensity": "warmup",
         "duration_type": "time", "duration_value": warmup_s,
         "target_type": "speed", "pace_low": pace_easy * 1.1, "pace_high": pace_easy * 0.95},
        {"type": "step", "name": "Allure tempo", "intensity": "active",
         "duration_type": "time", "duration_value": tempo_s,
         "target_type": "speed", "pace_low": pace_tempo * 1.03, "pace_high": pace_tempo * 0.97},
        {"type": "step", "name": "Retour au calme", "intensity": "cooldown",
         "duration_type": "time", "duration_value": cooldown_s,
         "target_type": "speed", "pace_low": pace_easy * 1.1, "pace_high": pace_easy * 0.95},
    ]


def _tcx_intervals(reps: int, interval_m: int, recovery_s: int,
                   pace_interval: float, pace_easy: float) -> list[dict]:
    return [
        {"type": "step", "name": "Échauffement", "intensity": "warmup",
         "duration_type": "time", "duration_value": _WARMUP_DURATION,
         "target_type": "speed", "pace_low": pace_easy * 1.1, "pace_high": pace_easy * 0.95},
        {
            "type": "repeat",
            "repetitions": reps,
            "steps": [
                {"type": "step", "name": f"Intervalle {interval_m}m", "intensity": "active",
                 "duration_type": "distance", "duration_value": interval_m,
                 "target_type": "speed", "pace_low": pace_interval * 1.03, "pace_high": pace_interval * 0.97},
                {"type": "step", "name": "Récupération", "intensity": "rest",
                 "duration_type": "time", "duration_value": recovery_s,
                 "target_type": "none"},
            ],
        },
        {"type": "step", "name": "Retour au calme", "intensity": "cooldown",
         "duration_type": "time", "duration_value": _COOLDOWN_DURATION,
         "target_type": "speed", "pace_low": pace_easy * 1.1, "pace_high": pace_easy * 0.95},
    ]


def _tcx_long_run(duration_min: float, pace_long: float) -> list[dict]:
    return [
        {"type": "step", "name": "Sortie longue", "intensity": "active",
         "duration_type": "time", "duration_value": int(duration_min * 60),
         "target_type": "speed", "pace_low": pace_long * 1.1, "pace_high": pace_long * 0.95},
    ]


def generate_plan(
    goal_date: date,
    goal_distance_km: float,
    goal_time_min: Optional[float] = None,
    goal_pace_min_km: Optional[float] = None,
    weekly_elevation_m: int = 0,
) -> list[dict]:
    """
    Génère un plan d'entraînement.

    Retourne une liste de semaines :
    {
        "week_num": int,
        "week_start": date,
        "week_end": date,
        "phase": str,
        "total_km": float,
        "sessions": [Session, ...]
    }
    """
    today = date.today()
    weeks_until = max(4, (goal_date - today).days // 7)

    # Allures de référence
    if goal_pace_min_km is None and goal_time_min and goal_distance_km:
        goal_pace_min_km = goal_time_min / goal_distance_km
    if not goal_pace_min_km:
        goal_pace_min_km = 6.0

    pace_easy = round(goal_pace_min_km * 1.25, 2)
    pace_long = round(goal_pace_min_km * 1.20, 2)
    pace_tempo = round(goal_pace_min_km * 1.08, 2)
    pace_interval = round(goal_pace_min_km * 0.95, 2)

    # Phases
    taper_weeks = min(3, max(2, weeks_until // 6))
    peak_weeks = max(1, weeks_until // 5)
    build_weeks = max(2, weeks_until // 3)
    base_weeks = max(0, weeks_until - build_weeks - peak_weeks - taper_weeks)

    def get_phase(remaining: int) -> str:
        if remaining <= taper_weeks:
            return "Affûtage"
        if remaining <= taper_weeks + peak_weeks:
            return "Pic"
        if remaining <= taper_weeks + peak_weeks + build_weeks:
            return "Construction"
        return "Base"

    # Démarrage le lundi suivant
    days_to_monday = (7 - today.weekday()) % 7
    if days_to_monday == 0:
        days_to_monday = 7
    week_start = today + timedelta(days=days_to_monday)

    plan: list[dict] = []

    for wn in range(weeks_until):
        remaining = weeks_until - wn
        phase = get_phase(remaining)
        progress = wn / max(1, weeks_until - taper_weeks)  # 0→1 pendant la montée en charge

        # Volume long run : part de 50% de la distance objectif, monte à 80-100%
        max_long_pct = 1.0 if goal_distance_km <= 10 else 0.90
        long_dist_km = round(goal_distance_km * min(max_long_pct, 0.5 + 0.5 * progress), 1)
        long_min = round(long_dist_km * pace_long, 0)

        # Durée tempo (minutes de travail réel)
        tempo_work_min = round(15 + 15 * progress, 0)  # 15 → 30 min

        # Intervals : 4×400m en base, jusqu'à 8×1000m en pic
        n_reps = int(4 + 4 * progress)
        interval_m = 400 if goal_distance_km <= 5 else (800 if goal_distance_km <= 21 else 1000)

        if phase == "Affûtage":
            long_min = round(long_min * (0.5 + 0.5 * (remaining / taper_weeks)), 0)
            long_dist_km = round(long_min / pace_long, 1)

        sessions: list[Session] = []

        # Structure hebdomadaire selon la phase
        # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
        if phase == "Base":
            schedule = {
                1: "EA", 3: "EA", 5: "LO",
            }
        elif phase == "Construction":
            schedule = {
                1: "EA", 2: "TE", 4: "EA", 5: "LO",
            }
        elif phase == "Pic":
            schedule = {
                1: "EA", 2: "TE", 3: "IT" if goal_distance_km <= 21 else "EA", 4: "EA", 5: "LO",
            }
        else:  # Affûtage
            schedule = {
                1: "EA", 2: "TE", 4: "EA",
            }

        for day_offset in range(7):
            sess_date = week_start + timedelta(days=day_offset)
            stype = schedule.get(day_offset, "REST")

            if stype == "REST":
                sessions.append(Session(
                    day=day_offset, date=sess_date,
                    type="REST", name="Repos",
                    description="Récupération active ou repos complet.",
                    duration_min=None, distance_km=None,
                    pace_target=None, pace_easy=pace_easy,
                    tcx_steps=[],
                ))

            elif stype == "EA":
                dur = 40 if phase == "Affûtage" else round(40 + 10 * progress, 0)
                dist = round(dur / pace_easy, 1)
                sessions.append(Session(
                    day=day_offset, date=sess_date,
                    type="EA", name=f"🟢 Endurance fondamentale {dur:.0f}min",
                    description=f"Footing facile {dur:.0f}min à ~{pace_easy:.0f}:{int((pace_easy%1)*60):02d}/km.",
                    duration_min=dur, distance_km=dist,
                    pace_target=pace_easy, pace_easy=pace_easy,
                    tcx_steps=_tcx_easy_run(dur, pace_easy),
                ))

            elif stype == "TE":
                total_dur = _WARMUP_DURATION / 60 + tempo_work_min + _COOLDOWN_DURATION / 60
                dist = round(total_dur / pace_tempo + (_WARMUP_DURATION / 60 + _COOLDOWN_DURATION / 60) / pace_easy, 1)
                sessions.append(Session(
                    day=day_offset, date=sess_date,
                    type="TE", name=f"🟡 Tempo {tempo_work_min:.0f}min",
                    description=(
                        f"10min échauffement + {tempo_work_min:.0f}min tempo "
                        f"à ~{pace_tempo:.0f}:{int((pace_tempo%1)*60):02d}/km + 10min retour calme."
                    ),
                    duration_min=total_dur, distance_km=dist,
                    pace_target=pace_tempo, pace_easy=pace_easy,
                    tcx_steps=_tcx_tempo(
                        _WARMUP_DURATION, int(tempo_work_min * 60), _COOLDOWN_DURATION,
                        pace_tempo, pace_easy,
                    ),
                ))

            elif stype == "IT":
                recov_s = 90 if interval_m <= 400 else 120
                interval_total_s = int(interval_m / 1000 * pace_interval * 60) * n_reps
                total_dur = (_WARMUP_DURATION + interval_total_s + recov_s * n_reps + _COOLDOWN_DURATION) / 60
                dist = round(n_reps * interval_m / 1000 + ((_WARMUP_DURATION + _COOLDOWN_DURATION) / 60) / pace_easy, 1)
                sessions.append(Session(
                    day=day_offset, date=sess_date,
                    type="IT", name=f"🔴 Intervalles {n_reps}×{interval_m}m",
                    description=(
                        f"10min écht + {n_reps}×{interval_m}m à ~{pace_interval:.0f}:{int((pace_interval%1)*60):02d}/km "
                        f"(récup {recov_s}s) + 10min calme."
                    ),
                    duration_min=round(total_dur, 0), distance_km=dist,
                    pace_target=pace_interval, pace_easy=pace_easy,
                    tcx_steps=_tcx_intervals(n_reps, interval_m, recov_s, pace_interval, pace_easy),
                ))

            elif stype == "LO":
                sessions.append(Session(
                    day=day_offset, date=sess_date,
                    type="LO", name=f"🔵 Sortie longue {long_dist_km}km",
                    description=(
                        f"Sortie longue {long_dist_km}km à ~{pace_long:.0f}:{int((pace_long%1)*60):02d}/km. "
                        "Restez à l'aise, capable de parler."
                    ),
                    duration_min=long_min, distance_km=long_dist_km,
                    pace_target=pace_long, pace_easy=pace_easy,
                    tcx_steps=_tcx_long_run(long_min, pace_long),
                ))

        total_km = sum(s.distance_km for s in sessions if s.distance_km)
        plan.append({
            "week_num": wn + 1,
            "week_start": week_start,
            "week_end": week_start + timedelta(days=6),
            "phase": phase,
            "total_km": round(total_km, 1),
            "sessions": sessions,
        })
        week_start += timedelta(weeks=1)

    # Semaine de course
    race_s = Session(
        day=5, date=week_start + timedelta(days=5),
        type="RP",
        name=f"🏁 COURSE — {goal_distance_km}km",
        description=f"Objectif : {goal_distance_km}km en {goal_time_min:.0f}min" if goal_time_min else f"Course {goal_distance_km}km",
        duration_min=goal_time_min, distance_km=goal_distance_km,
        pace_target=goal_pace_min_km, pace_easy=pace_easy,
        tcx_steps=[],
    )
    plan.append({
        "week_num": weeks_until + 1,
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "phase": "Course",
        "total_km": goal_distance_km,
        "sessions": [race_s],
    })

    return plan
