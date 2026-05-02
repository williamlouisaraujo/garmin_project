import json
import os
from garminconnect import Garmin

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

if not EMAIL or not PASSWORD:
    raise SystemExit("Définis GARMIN_EMAIL et GARMIN_PASSWORD dans tes variables d'environnement.")

client = Garmin(EMAIL, PASSWORD)
client.login()

pr = client.get_personal_record()
pred = client.get_race_predictions()

print("=== get_personal_record() ===")
print(json.dumps(pr, indent=2, ensure_ascii=False, default=str))

print("\n=== get_race_predictions() ===")
print(json.dumps(pred, indent=2, ensure_ascii=False, default=str))