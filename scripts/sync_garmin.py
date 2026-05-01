"""Script de synchronisation Garmin -> Supabase (squelette initial)."""

from src.garmin_client import get_client


def main() -> None:
    client = get_client()
    activities = client.get_activities(0, 20)
    print(f"{len(activities)} activités récupérées.")


if __name__ == "__main__":
    main()