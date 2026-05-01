"""Génération de plan d'entraînement course à pied — allures basées sur la VMA."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


def _race_pct_vma(goal_time_min: float) -> float:
    """% de VMA soutenable en fonction de la durée de course (modèle de Péronnet-Thibault)."""
    if goal_time_min <= 10:   return 1.00
    if goal_time_min <= 20:   return 0.97
    if goal_time_min <= 40:   return 0.93
    if goal_time_min <= 80:   return 0.88
    if goal_time_min <= 150:  return 0.83
    if goal_time_min <= 250:  return 0.78
    return 0.72


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
    pace_easy: Optional[float]
    tcx_steps: list[dict] = field(default_factory=list)


_WARMUP  = 600   # 10 min en secondes
_COOLDOWN = 600


def _tcx_easy(duration_min: float, p: float) -> list[dict]:
    return [{
        "type": "step", "name": "Footing",
        "intensity": "active", "duration_type": "time",
        "duration_value": int(duration_min * 60),
        "target_type": "speed", "pace_low": p * 1.10, "pace_high": p * 0.95,
    }]


def _tcx_tempo(tempo_s: int, p_tempo: float, p_easy: float) -> list[dict]:
    return [
        {"type": "step", "name": "Échauffement", "intensity": "warmup",
         "duration_type": "time", "duration_value": _WARMUP,
         "target_type": "speed", "pace_low": p_easy * 1.10, "pace_high": p_easy * 0.95},
        {"type": "step", "name": "Allure tempo", "intensity": "active",
         "duration_type": "time", "duration_value": tempo_s,
         "target_type": "speed", "pace_low": p_tempo * 1.02, "pace_high": p_tempo * 0.98},
        {"type": "step", "name": "Retour au calme", "intensity": "cooldown",
         "duration_type": "time", "duration_value": _COOLDOWN,
         "target_type": "speed", "pace_low": p_easy * 1.10, "pace_high": p_easy * 0.95},
    ]


def _tcx_intervals(reps: int, m: int, rec_s: int,
                   p_interval: float, p_easy: float) -> list[dict]:
    return [
        {"type": "step", "name": "Échauffement", "intensity": "warmup",
         "duration_type": "time", "duration_value": _WARMUP,
         "target_type": "speed", "pace_low": p_easy * 1.10, "pace_high": p_easy * 0.95},
        {"type": "repeat", "repetitions": reps, "steps": [
            {"type": "step", "name": f"{m}m", "intensity": "active",
             "duration_type": "distance", "duration_value": m,
             "target_type": "speed", "pace_low": p_interval * 1.02, "pace_high": p_interval * 0.98},
            {"type": "step", "name": "Récup", "intensity": "rest",
             "duration_type": "time", "duration_value": rec_s, "target_type": "none"},
        ]},
        {"type": "step", "name": "Retour au calme", "intensity": "cooldown",
         "duration_type": "time", "duration_value": _COOLDOWN,
         "target_type": "speed", "pace_low": p_easy * 1.10, "pace_high": p_easy * 0.95},
    ]


def _tcx_long(duration_min: float, p_long: float) -> list[dict]:
    return [{
        "type": "step", "name": "Sortie longue",
        "intensity": "active", "duration_type": "time",
        "duration_value": int(duration_min * 60),
        "target_type": "speed", "pace_low": p_long * 1.08, "pace_high": p_long * 0.95,
    }]


def _fmt_pace(p: float) -> str:
    m = int(p)
    s = int(round((p - m) * 60))
    if s == 60:
        m += 1; s = 0
    return f"{m}:{s:02d}"


def generate_plan(
    goal_date: date,
    goal_distance_km: float,
    goal_time_min: Optional[float] = None,
    goal_pace_min_km: Optional[float] = None,
    weekly_elevation_m: int = 0,
    vma_kmh: Optional[float] = None,
) -> list[dict]:
    """
    Génère un plan d'entraînement.

    Si vma_kmh est fourni, toutes les allures sont dérivées de la VMA et
    l'allure course est calculée en fonction de la durée estimée (%VMA selon
    le modèle de Péronnet-Thibault).
    Sinon, les allures sont dérivées de l'allure objectif.

    Retourne une liste de semaines :
      week_num, week_start, week_end, phase, total_km, sessions: [Session]
    """
    today = date.today()
    weeks_until = max(4, (goal_date - today).days // 7)

    # ── Allures de base ───────────────────────────────────────────────────────
    if vma_kmh and vma_kmh > 0:
        vma_pace = 60.0 / vma_kmh          # min/km à VMA

        # Allure course selon durée (VMA × %VMA)
        if goal_time_min and goal_time_min > 0:
            pct = _race_pct_vma(goal_time_min)
            race_pace = round(vma_pace / pct, 3)
        elif goal_pace_min_km:
            race_pace = goal_pace_min_km
            # Recalcul approximatif du %VMA
            pct = round(vma_pace / race_pace, 3)
        else:
            # Estimer l'allure à partir de la distance et de la VMA
            # Approximation : pace_race ≈ vma_pace / %VMA(dist_based)
            approx_pct = 0.85 if goal_distance_km <= 10 else 0.78
            race_pace = round(vma_pace / approx_pct, 3)
            pct = approx_pct

        pace_easy     = round(vma_pace / 0.68, 3)   # Zone 2 : ~68% VMA
        pace_long     = round(vma_pace / 0.72, 3)   # Zone 2-3 : ~72% VMA
        pace_tempo    = round(vma_pace / 0.86, 3)   # Zone 4 : ~86% VMA
        pace_interval = round(vma_pace / 0.97, 3)   # Zone 5 : ~97% VMA
        goal_pace_min_km = race_pace

        vma_info = f"VMA {vma_kmh} km/h — {_fmt_pace(vma_pace)}/km"
    else:
        # Fallback : allures relatives à l'allure objectif
        if not goal_pace_min_km and goal_time_min and goal_distance_km:
            goal_pace_min_km = round(goal_time_min / goal_distance_km, 3)
        if not goal_pace_min_km:
            goal_pace_min_km = 6.0

        pace_easy     = round(goal_pace_min_km * 1.28, 3)
        pace_long     = round(goal_pace_min_km * 1.22, 3)
        pace_tempo    = round(goal_pace_min_km * 1.08, 3)
        pace_interval = round(goal_pace_min_km * 0.95, 3)
        race_pace     = goal_pace_min_km
        vma_info      = "VMA non renseignée — allures relatives à l'objectif"

    # ── Phases ───────────────────────────────────────────────────────────────
    taper_weeks = min(3, max(2, weeks_until // 6))
    peak_weeks  = max(1, weeks_until // 5)
    build_weeks = max(2, weeks_until // 3)

    def get_phase(remaining: int) -> str:
        if remaining <= taper_weeks:                            return "Affûtage"
        if remaining <= taper_weeks + peak_weeks:               return "Pic"
        if remaining <= taper_weeks + peak_weeks + build_weeks: return "Construction"
        return "Base"

    days_to_monday = (7 - today.weekday()) % 7 or 7
    week_start = today + timedelta(days=days_to_monday)
    plan: list[dict] = []

    for wn in range(weeks_until):
        remaining = weeks_until - wn
        phase = get_phase(remaining)
        progress = wn / max(1, weeks_until - taper_weeks)

        # Volume sortie longue
        max_long_pct = 1.0 if goal_distance_km <= 10 else 0.90
        long_dist = round(goal_distance_km * min(max_long_pct, 0.50 + 0.50 * progress), 1)
        long_min  = round(long_dist * pace_long, 0)
        if phase == "Affûtage":
            long_min  = round(long_min * (0.50 + 0.50 * (remaining / taper_weeks)), 0)
            long_dist = round(long_min / pace_long, 1)

        # Tempo work
        tempo_work_min = round(15 + 15 * progress, 0)

        # Intervalles
        n_reps     = int(4 + 4 * progress)
        interval_m = 400 if goal_distance_km <= 5 else (800 if goal_distance_km <= 21 else 1000)
        recov_s    = 90 if interval_m <= 400 else 120

        # Structure hebdomadaire
        if phase == "Base":
            schedule = {1: "EA", 3: "EA", 5: "LO"}
        elif phase == "Construction":
            schedule = {1: "EA", 2: "TE", 4: "EA", 5: "LO"}
        elif phase == "Pic":
            schedule = {1: "EA", 2: "TE",
                        3: "IT" if goal_distance_km <= 21 else "EA",
                        4: "EA", 5: "LO"}
        else:  # Affûtage
            schedule = {1: "EA", 2: "TE", 4: "EA"}

        sessions: list[Session] = []
        for day in range(7):
            sess_date = week_start + timedelta(days=day)
            stype = schedule.get(day, "REST")

            if stype == "REST":
                sessions.append(Session(
                    day=day, date=sess_date, type="REST", name="Repos",
                    description="Récupération ou repos complet.",
                    duration_min=None, distance_km=None,
                    pace_target=None, pace_easy=pace_easy,
                ))

            elif stype == "EA":
                dur  = 40 if phase == "Affûtage" else round(40 + 10 * progress, 0)
                dist = round(dur / pace_easy, 1)
                sessions.append(Session(
                    day=day, date=sess_date, type="EA",
                    name=f"🟢 EF {dur:.0f}min — {_fmt_pace(pace_easy)}/km",
                    description=f"Footing confortable {dur:.0f}min à {_fmt_paste(pace_easy)}. Vous devez pouvoir parler sans effort.",
                    duration_min=dur, distance_km=dist,
                    pace_target=pace_easy, pace_easy=pace_easy,
                    tcx_steps=_tcx_easy(dur, pace_easy),
                ))

            elif stype == "TE":
                total_dur = (_WARMUP + int(tempo_work_min * 60) + _COOLDOWN) / 60
                dist = round(total_dur / 60 * (60 / pace_tempo), 1)  # approx
                sessions.append(Session(
                    day=day, date=sess_date, type="TE",
                    name=f"🟡 Tempo {tempo_work_min:.0f}min — {_fmt_pace(pace_tempo)}/km",
                    description=(
                        f"10min écht + {tempo_work_min:.0f}min à {_fmt_pace(pace_tempo)}/km "
                        f"(86% VMA) + 10min calme. Effort contrôlé, respiration rapide mais régulière."
                    ),
                    duration_min=round(total_dur, 0), distance_km=dist,
                    pace_target=pace_tempo, pace_easy=pace_easy,
                    tcx_steps=_tcx_tempo(int(tempo_work_min * 60), pace_tempo, pace_easy),
                ))

            elif stype == "IT":
                total_dur = (_WARMUP + int(interval_m / 1000 * pace_interval * 60) * n_reps +
                             recov_s * n_reps + _COOLDOWN) / 60
                dist = round(n_reps * interval_m / 1000
                             + (_WARMUP + _COOLDOWN) / 60 / pace_easy, 1)
                sessions.append(Session(
                    day=day, date=sess_date, type="IT",
                    name=f"🔴 {n_reps}×{interval_m}m — {_fmt_pace(pace_interval)}/km",
                    description=(
                        f"10min écht + {n_reps}×{interval_m}m à {_fmt_pace(pace_interval)}/km "
                        f"(97% VMA), récup {recov_s}s + 10min calme."
                    ),
                    duration_min=round(total_dur, 0), distance_km=dist,
                    pace_target=pace_interval, pace_easy=pace_easy,
                    tcx_steps=_tcx_intervals(n_reps, interval_m, recov_s, pace_interval, pace_easy),
                ))

            elif stype == "LO":
                sessions.append(Session(
                    day=day, date=sess_date, type="LO",
                    name=f"🔵 Longue {long_dist}km — {_fmt_pace(pace_long)}/km",
                    description=(
                        f"Sortie longue {long_dist}km à {_fmt_pace(pace_long)}/km "
                        f"(72% VMA). Allure conversationnelle, hydratation régulière."
                    ),
                    duration_min=long_min, distance_km=long_dist,
                    pace_target=pace_long, pace_easy=pace_easy,
                    tcx_steps=_tcx_long(long_min, pace_long),
                ))

        total_km = sum(s.distance_km for s in sessions if s.distance_km)
        plan.append({
            "week_num": wn + 1,
            "week_start": week_start,
            "week_end": week_start + timedelta(days=6),
            "phase": phase,
            "total_km": round(total_km, 1),
            "vma_info": vma_info,
            "sessions": sessions,
        })
        week_start += timedelta(weeks=1)

    # Semaine de course
    race_note = ""
    if vma_kmh and goal_time_min:
        race_note = (
            f"Allure cible : {_fmt_pace(race_pace)}/km "
            f"({round(_race_pct_vma(goal_time_min)*100)}% VMA pour {goal_time_min:.0f}min de course)"
        )
    plan.append({
        "week_num": weeks_until + 1,
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "phase": "Course",
        "total_km": goal_distance_km,
        "vma_info": vma_info,
        "sessions": [Session(
            day=5, date=week_start + timedelta(days=5),
            type="RP", name=f"🏁 COURSE — {goal_distance_km}km",
            description=race_note or f"Objectif : {goal_distance_km}km",
            duration_min=goal_time_min, distance_km=goal_distance_km,
            pace_target=race_pace, pace_easy=pace_easy,
        )],
    })

    return plan


def _fmt_paste(p: float) -> str:  # alias interne utilisé dans description
    return _fmt_pace(p)
