"""Générateur de fichiers TCX (Training Center XML) pour les séances d'entraînement.
Les fichiers TCX peuvent être importés dans Garmin Connect et envoyés à la montre.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOC = f"{NS} https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"


def _pace_to_ms(pace_min_km: float) -> float:
    """Convertit une allure (min/km) en vitesse (m/s)."""
    return 1000.0 / (pace_min_km * 60.0)


def _add_step(parent: ET.Element, step_def: dict, step_id_counter: list[int]) -> None:
    """Ajoute récursivement un step ou un bloc repeat au parent XML."""
    stype = step_def.get("type", "step")

    if stype == "repeat":
        el = ET.SubElement(parent, "Step")
        el.set(f"{{{XSI}}}type", "Repeat_t")
        ET.SubElement(el, "StepId").text = str(step_id_counter[0])
        step_id_counter[0] += 1
        ET.SubElement(el, "Repetitions").text = str(step_def.get("repetitions", 1))
        for child in step_def.get("steps", []):
            _add_step(el, child, step_id_counter)
        return

    el = ET.SubElement(parent, "Step")
    el.set(f"{{{XSI}}}type", "Step_t")
    ET.SubElement(el, "StepId").text = str(step_id_counter[0])
    step_id_counter[0] += 1

    if step_def.get("name"):
        ET.SubElement(el, "Name").text = step_def["name"]

    # Duration
    dur = ET.SubElement(el, "Duration")
    dur_type = step_def.get("duration_type", "open")
    if dur_type == "time":
        dur.set(f"{{{XSI}}}type", "Time_t")
        ET.SubElement(dur, "Seconds").text = str(int(step_def.get("duration_value", 0)))
    elif dur_type == "distance":
        dur.set(f"{{{XSI}}}type", "Distance_t")
        ET.SubElement(dur, "Meters").text = str(int(step_def.get("duration_value", 0)))
    else:
        dur.set(f"{{{XSI}}}type", "UserInitiated_t")

    # Intensity
    intensity_map = {"active": "Active", "rest": "Rest", "warmup": "Active", "cooldown": "Active"}
    ET.SubElement(el, "Intensity").text = intensity_map.get(step_def.get("intensity", "active"), "Active")

    # Target
    tgt = ET.SubElement(el, "Target")
    if step_def.get("target_type") == "speed" and step_def.get("pace_low") and step_def.get("pace_high"):
        tgt.set(f"{{{XSI}}}type", "Speed_t")
        zone = ET.SubElement(tgt, "SpeedZone")
        zone.set(f"{{{XSI}}}type", "CustomSpeedZone_t")
        lo = _pace_to_ms(max(step_def["pace_low"], step_def["pace_high"]))  # slower
        hi = _pace_to_ms(min(step_def["pace_low"], step_def["pace_high"]))  # faster
        ET.SubElement(zone, "LowInMetersPerSecond").text = f"{lo:.4f}"
        ET.SubElement(zone, "HighInMetersPerSecond").text = f"{hi:.4f}"
    else:
        tgt.set(f"{{{XSI}}}type", "None_t")


def generate_tcx(
    name: str,
    steps: list[dict],
    sport: str = "Running",
    notes: Optional[str] = None,
) -> str:
    """
    Génère un fichier TCX pour une séance d'entraînement.

    Chaque step est un dict :
      {
        "type": "step" | "repeat",
        "name": str,
        "intensity": "active" | "rest" | "warmup" | "cooldown",
        "duration_type": "time" | "distance" | "open",
        "duration_value": int,   # secondes ou mètres
        "target_type": "speed" | "none",
        "pace_low": float,   # allure max (plus lente, en min/km)
        "pace_high": float,  # allure min (plus rapide, en min/km)
        # Pour repeat :
        "repetitions": int,
        "steps": [...]
      }
    """
    root = ET.Element("TrainingCenterDatabase")
    root.set("xmlns", NS)
    root.set("xmlns:xsi", XSI)
    root.set("xsi:schemaLocation", SCHEMA_LOC)

    workouts = ET.SubElement(root, "Workouts")
    workout = ET.SubElement(workouts, "Workout")
    workout.set("Sport", sport)
    ET.SubElement(workout, "Name").text = name

    counter = [1]
    for step in steps:
        _add_step(workout, step, counter)

    if notes:
        ET.SubElement(workout, "Notes").text = notes

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")
