import json
import os
from datetime import date
from garminconnect import Garmin


def jprint(title: str, data):
    print(f"\n=== {title} ===")
    try:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    except Exception:
        print(data)


def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {"__error__": str(exc), "__fn__": getattr(fn, "__name__", "unknown")}


def extract_vo2max(data):
    if not data:
        return None
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k in ("vo2MaxPreciseValue", "vo2MaxValue", "value"):
                    if item.get(k) is not None:
                        try:
                            return float(item[k])
                        except Exception:
                            pass
    if isinstance(data, dict):
        metrics = data.get("allMetrics", {}).get("metricsMap", {})
        for key in ("METRIC_VO2_MAX_RUNNING", "METRIC_VO2_MAX"):
            vals = metrics.get(key, [])
            if vals and isinstance(vals[-1], dict):
                v = vals[-1].get("value")
                if v is not None:
                    try:
                        return float(v)
                    except Exception:
                        pass
        for k in ("vo2MaxPreciseValue", "vo2MaxValue"):
            if data.get(k) is not None:
                try:
                    return float(data[k])
                except Exception:
                    pass
    return None


def extract_lt(data):
    """Retourne (hr, speed_raw, pace_min_km)."""
    if not data:
        return None, None, None

    item = data[0] if isinstance(data, list) and data else data
    if not isinstance(item, dict):
        return None, None, None

    hr = item.get("lactateThresholdHeartRate") or item.get("heartRate")
    speed = item.get("lactateThresholdSpeed") or item.get("speed")

    nested = item.get("speed_and_heart_rate", {})
    if isinstance(nested, dict):
        hr = hr or nested.get("heartRate")
        speed = speed or nested.get("speed")

    speed_val = None
    try:
        speed_val = float(speed) if speed is not None else None
    except Exception:
        speed_val = None

    pace = None
    if speed_val and speed_val > 0:
        # hypothèse m/s <= 12, sinon km/h
        if speed_val <= 12:
            pace = 1000 / (speed_val * 60)
        else:
            pace = 60 / speed_val

    return (int(hr) if hr else None), speed_val, pace


def extract_fcmax(data):
    if not isinstance(data, dict):
        return None
    for k in ("maxHrpm", "maxHeartRate", "max_heart_rate"):
        if data.get(k) is not None:
            try:
                return int(data[k])
            except Exception:
                pass
    return None


def extract_readiness(data):
    if not data:
        return None
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        for k in ("score", "trainingReadinessScore", "value"):
            if data.get(k) is not None:
                try:
                    return int(data[k])
                except Exception:
                    pass
    return None


def main():
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise SystemExit(
            "Définis GARMIN_EMAIL et GARMIN_PASSWORD dans tes variables d'environnement."
        )

    today = date.today().isoformat()

    client = Garmin(email, password)
    client.login()

    # appels bruts
    vo2max_raw = safe_call(client.get_max_metrics, today)
    lt_raw = safe_call(client.get_lactate_threshold, latest=True)
    profile_raw = safe_call(client.get_userprofile_settings)
    readiness_raw = safe_call(client.get_training_readiness, today)

    # fallback VO2max sur 30 jours
    vo2_history = []
    for i in range(30):
        d = date.fromordinal(date.today().toordinal() - i).isoformat()
        payload = safe_call(client.get_max_metrics, d)
        vo2_history.append({"date": d, "payload": payload})

    # affichage brut
    jprint("get_max_metrics(today)", vo2max_raw)
    jprint("get_lactate_threshold(latest=True)", lt_raw)
    jprint("get_userprofile_settings()", profile_raw)
    jprint("get_training_readiness(today)", readiness_raw)

    # extraction synthétique
    vo2_today = extract_vo2max(vo2max_raw)

    vo2_hist_value = None
    vo2_hist_date = None
    for row in vo2_history:
        v = extract_vo2max(row["payload"])
        if v is not None:
            vo2_hist_value = v
            vo2_hist_date = row["date"]
            break

    lt_hr, lt_speed, lt_pace = extract_lt(lt_raw)
    fcmax = extract_fcmax(profile_raw)
    readiness = extract_readiness(readiness_raw)

    print("\n=== SYNTHÈSE ===")
    print(f"VO2max (today): {vo2_today}")
    print(f"VO2max (fallback 30j): {vo2_hist_value} (date={vo2_hist_date})")
    print(f"LT HR: {lt_hr}")
    print(f"LT speed raw: {lt_speed}")
    print(f"LT pace (min/km): {lt_pace}")
    print(f"FC max profile: {fcmax}")
    print(f"Training readiness: {readiness}")

    print("\n=== VO2 HISTORY (dates with value) ===")
    for row in vo2_history:
        v = extract_vo2max(row["payload"])
        if v is not None:
            print(f"- {row['date']}: {v}")


if __name__ == "__main__":
    main()