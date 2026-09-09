import json
import os
from datetime import datetime, timezone

import requests


API_URL = "https://danepubliczne.imgw.pl/api/data/hydro/"
JSON_FILE = "dane.json"

# Stacja zostanie wybrana po nazwie/rzece.
# Jeżeli IMGW zwróci kilka podobnych stacji, wybieramy tę
# najbardziej odpowiadającą Jeziorsku.
STATION_NAMES = [
    "Skęczniew",
    "Skecznie",
    "Jeziorsko",
]


def get_hydro_data():
    """Pobiera aktualne dane hydrologiczne z IMGW."""
    response = requests.get(
        API_URL,
        timeout=30,
        headers={
            "User-Agent": "jeziorsko-monitoring/1.0"
        },
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("IMGW zwróciło dane w nieoczekiwanym formacie.")

    return data


def find_station(data):
    """Znajduje stację Jeziorsko / Skęczniew."""

    # Najpierw szukamy po nazwie stacji.
    for preferred_name in STATION_NAMES:
        for station in data:
            name = str(station.get("stacja") or "").strip().lower()

            if name == preferred_name.lower():
                return station

    # Następnie szukamy nazwy zawierającej Skęczniew/Jeziorsko.
    for station in data:
        name = str(station.get("stacja") or "").lower()

        if any(
            value.lower() in name
            for value in STATION_NAMES
        ):
            return station

    # Ostatecznie szukamy stacji na Warcie w okolicy Jeziorska.
    for station in data:
        river = str(station.get("rzeka") or "").lower()

        if river == "warta":
            lat = station.get("lat")
            lon = station.get("lon")

            if lat is not None and lon is not None:
                try:
                    lat = float(lat)
                    lon = float(lon)

                    # Przybliżony obszar Jeziorska.
                    if 51.7 <= lat <= 52.2 and 18.3 <= lon <= 19.0:
                        return station
                except (TypeError, ValueError):
                    pass

    raise RuntimeError(
        "Nie znaleziono stacji Jeziorsko/Skęczniew w API IMGW."
    )


def load_history():
    """Wczytuje istniejącą historię."""
    if not os.path.exists(JSON_FILE):
        return []

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

    except (json.JSONDecodeError, OSError):
        pass

    return []


def save_history(history):
    """Zapisuje historię w bezpieczny sposób."""
    temp_file = JSON_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(temp_file, JSON_FILE)


def parse_number(value):
    """Bezpiecznie zamienia wartość na float."""
    if value in (None, "", "-", "null"):
        return None

    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def build_record(station):
    """Buduje rekord zapisany w dane.json."""

    measurement_time = station.get("stan_wody_data_pomiaru")

    if not measurement_time:
        raise RuntimeError(
            "IMGW nie podało czasu pomiaru stanu wody."
        )

    stan_wody = parse_number(station.get("stan_wody"))
    przeplyw = parse_number(station.get("przeplyw"))

    # Rzędna zwierciadła:
    # stan wody jest podawany względem zera wodowskazu.
    zero_wodowskazu = parse_number(
        station.get("rzedna_zerawodowskazu")
    )

    rzedna = None

    if stan_wody is not None and zero_wodowskazu is not None:
        rzedna = round(
            zero_wodowskazu + stan_wody / 100,
            3,
        )

    return {
        "data": measurement_time,
        "stacja": station.get("stacja"),
        "rzeka": station.get("rzeka"),
        "id_stacji": station.get("id_stacji"),
        "stan_wody": stan_wody,
        "rzedna": rzedna,
        "przeplyw": przeplyw,
        "stan_alarmowy": parse_number(
            station.get("stan_alarmowy")
        ),
        "stan_ostrzegawczy": parse_number(
            station.get("stan_ostrzegawczy")
        ),
        "pobrano": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def update():
    print("Pobieranie danych IMGW...")

    data = get_hydro_data()

    station = find_station(data)

    print(
        f"Znaleziono stację: "
        f"{station.get('stacja')} "
        f"(ID: {station.get('id_stacji')})"
    )

    record = build_record(station)

    print(
        f"Pomiar: {record['data']}, "
        f"stan: {record['stan_wody']} cm, "
        f"przepływ: {record['przeplyw']} m3/s"
    )

    history = load_history()

    # Nie dodajemy tego samego pomiaru drugi raz.
    existing_dates = {
        item.get("data")
        for item in history
        if isinstance(item, dict)
    }

    if record["data"] in existing_dates:
        print("Ten pomiar już znajduje się w historii.")
        return

    # Najnowszy pomiar na początku.
    history.insert(0, record)

    # Zachowujemy maksymalnie około 2 lat historii.
    history = history[:17520]

    save_history(history)

    print(
        f"OK — zapisano pomiar. "
        f"Liczba rekordów: {len(history)}"
    )


if __name__ == "__main__":
    try:
        update()
    except Exception as error:
        print(f"BŁĄD: {error}")
        raise
