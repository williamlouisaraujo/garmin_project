import os
from garminconnect import Garmin


def get_client() -> Garmin:
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise ValueError("GARMIN_EMAIL / GARMIN_PASSWORD manquants")

    client = Garmin(email, password)
    client.login()
    return client