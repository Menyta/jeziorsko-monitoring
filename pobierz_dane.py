import json
import os
import unicodedata
from datetime import datetime, timezone

import requests


# ============================================================
# KONFIGURACJA
# ============================================================

API_URL = "https://danepubliczne.imgw.pl/api/data/hydro/"
JSON_FILE = "dane.json"

# Nazwy stacji, które mogą być związane bezpośrednio
# ze zbiornikiem Jeziorsko.
ALLOWED_STATION_NAMES = {
    "skecz­niew",
    "skeczniew",
    "jeziorsko",
    "siedlatkow",
    "siedlątków",
}

# Maksymalna liczba zapisanych pomiarów.
# Przy pomiarze co godzinę daje to około 2 lat historii.
MAX_HISTORY = 17520


# ============================================================
# POMOCNICZE
# ============================================================

def normalize_text(value):
    """
    Usuwa polskie znaki, spacje i normalizuje nazwę.
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    return value.replace(" ", "")


def parse_number(value):
    """
    Bezpiecznie zamienia wartość na float.
    """

    if value in (
        None,
        "",
        "-",
        "null",
        "None",
    ):
        return None

    try:
        return float(
            str(value)
            .replace(",", ".")
            .strip()
        )
    except (TypeError, ValueError):
        return None


# ============================================================
# IMGW
# ============================================================

def get_hydro_data():
    """
    Pobiera aktualne dane hydrologiczne IMGW.
    """

    print("Pobieranie danych z IMGW...")

    response = requests.get(
        API_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "Jeziorsko-Monitoring/1.0"
            )
        },
    )

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as error:
        raise RuntimeError(
            "IMGW zwróciło odpowiedź, "
            "której nie można odczytać jako JSON."
        ) from error

    if not isinstance(data, list):
        raise RuntimeError(
            "IMGW zwróciło dane w nieoczekiwanym formacie."
        )

    print(
        f"IMGW zwróciło {len(data)} stacji."
    )

    return data


# ============================================================
# WYBÓR STACJI
# ============================================================

def find_jeziorsko_stations(data):
    """
    Szuka stacji o nazwach jednoznacznie związanych
    z Jeziorskiem.

    UWAGA:
    Nie stosujemy tutaj wyszukiwania po samej rzece Warta
    ani po przybliżonych współrzędnych.

    Dzięki temu Koło, Sieradz itd. nie zostaną przypadkowo
    potraktowane jako Jeziorsko.
    """

    matches = []

    for station in data:

        name = station.get("stacja")

        normalized_name = normalize_text(name)

        if normalized_name in {
            "skeczniew",
            "jeziorsko",
            "siedlatkow",
        }:
            matches.append(station)

    return matches


def find_station(data):
    """
    Zwraca jedną właściwą stację.

    Jeżeli API nie pozwala jednoznacznie wskazać stacji,
    zatrzymujemy program zamiast zapisywać błędne dane.
    """

    matches = find_jeziorsko_stations(data)

    if not matches:
        raise RuntimeError(
            "\n"
            "NIE ZNALEZIONO WŁAŚCIWEJ STACJI IMGW.\n"
            "\n"
            "API IMGW nie zwróciło stacji o nazwie "
            "Skęczniew / Jeziorsko / Siedlątków.\n"
            "\n"
            "Dla bezpieczeństwa NIE zapisuję danych "
            "z innej stacji.\n"
            "\n"
            "To celowe zachowanie — nie chcemy ponownie "
            "zapisać np. Koła jako Jeziorsko.\n"
        )

    if len(matches) > 1:

        print(
            "Znaleziono kilka potencjalnych stacji:"
        )

        for station in matches:
            print(
                f"  - {station.get('stacja')} "
                f"(ID: {station.get('id_stacji')})"
            )

        # Preferujemy Skęczniew.
        for station in matches:

            if (
                normalize_text(
                    station.get("stacja")
                )
                == "skeczniew"
            ):
                return station

        # Następnie Jeziorsko.
        for station in matches:

            if (
                normalize_text(
                    station.get("stacja")
                )
                == "jeziorsko"
            ):
                return station

        # Jeżeli nadal jest kilka, nie zgadujemy.
        raise RuntimeError(
            "Znaleziono kilka potencjalnych stacji "
            "Jeziorsko i nie można jednoznacznie "
            "wybrać właściwej."
        )

    return matches[0]


# ============================================================
# HISTORIA
# ============================================================

def load_history():
    """
    Wczytuje istniejącą historię z dane.json.
    """

    if not os.path.exists(JSON_FILE):
        return []

    try:

        with open(
            JSON_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if isinstance(data, list):
            return data

        print(
            "UWAGA: dane.json nie zawiera listy. "
            "Rozpoczynam nową historię."
        )

    except json.JSONDecodeError:

        print(
            "UWAGA: dane.json zawiera niepoprawny JSON. "
            "Rozpoczynam nową historię."
        )

    except OSError as error:

        print(
            f"UWAGA: nie można odczytać dane.json: {error}"
        )

    return []


def save_history(history):
    """
    Bezpiecznie zapisuje historię.

    Najpierw zapisujemy plik tymczasowy,
    dopiero potem podmieniamy dane.json.
    """

    temp_file = JSON_FILE + ".tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            history,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.write("\n")

    os.replace(
        temp_file,
        JSON_FILE,
    )


# ============================================================
# REKORD
# ============================================================

def calculate_rzedna(station):
    """
    Próbuje obliczyć rzędną zwierciadła wody.

    IMGW podaje:
      - rzędną zera wodowskazu
      - stan wody w cm

    Jeżeli któregoś parametru brakuje,
    zwracamy None zamiast wymyślać wartość.
    """

    stan_wody = parse_number(
        station.get("stan_wody")
    )

    zero_wodowskazu = parse_number(
        station.get("rzedna_zerawodowskazu")
    )

    if (
        stan_wody is None
        or zero_wodowskazu is None
    ):
        return None

    return round(
        zero_wodowskazu
        + stan_wody / 100.0,
        3,
    )


def build_record(station):
    """
    Tworzy rekord do dane.json.
    """

    measurement_time = (
        station.get(
            "stan_wody_data_pomiaru"
        )
    )

    if not measurement_time:

        raise RuntimeError(
            "IMGW nie podało czasu pomiaru "
            "stanu wody."
        )

    record = {
        "data": measurement_time,

        "stacja": station.get(
            "stacja"
        ),

        "rzeka": station.get(
            "rzeka"
        ),

        "id_stacji": station.get(
            "id_stacji"
        ),

        "stan_wody": parse_number(
            station.get("stan_wody")
        ),

        "rzedna": calculate_rzedna(
            station
        ),

        "przeplyw": parse_number(
            station.get("przeplyw")
        ),

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

    return record


# ============================================================
# DODAWANIE DO HISTORII
# ============================================================

def add_record(history, record):
    """
    Dodaje rekord, jeżeli taki pomiar nie istnieje.
    """

    measurement_time = record.get(
        "data"
    )

    station_id = record.get(
        "id_stacji"
    )

    for item in history:

        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("data")
            == measurement_time
            and
            item.get("id_stacji")
            == station_id
        ):
            print(
                "Ten pomiar już istnieje "
                "w dane.json."
            )

            return history

    history.append(record)

    # Najnowsze na początku.
    history.sort(
        key=lambda item: (
            item.get("data")
            or ""
        ),
        reverse=True,
    )

    # Ograniczenie historii.
    history = history[
        :MAX_HISTORY
    ]

    return history


# ============================================================
# GŁÓWNA FUNKCJA
# ============================================================

def update():

    print("=" * 60)
    print("JEZIORSKO MONITORING")
    print("Aktualizacja danych IMGW")
    print("=" * 60)

    # 1. Pobierz dane IMGW.
    data = get_hydro_data()

    # 2. Znajdź właściwą stację.
    station = find_station(data)

    print()
    print("ZNALEZIONA STACJA:")
    print(
        f"  Nazwa:     {station.get('stacja')}"
    )
    print(
        f"  Rzeka:     {station.get('rzeka')}"
    )
    print(
        f"  ID:        {station.get('id_stacji')}"
    )
    print()

    # 3. Utwórz rekord.
    record = build_record(
        station
    )

    print("POMIAR:")
    print(
        f"  Czas:      {record.get('data')}"
    )
    print(
        f"  Stan:      {record.get('stan_wody')} cm"
    )
    print(
        f"  Rzędna:    {record.get('rzedna')} m"
    )
    print(
        f"  Przepływ:  {record.get('przeplyw')} m3/s"
    )
    print(
        f"  Alarmowy:  {record.get('stan_alarmowy')} cm"
    )
    print(
        f"  Ostrzeg.:  {record.get('stan_ostrzegawczy')} cm"
    )
    print()

    # 4. Wczytaj historię.
    history = load_history()

    old_count = len(history)

    # 5. Dodaj pomiar.
    history = add_record(
        history,
        record,
    )

    new_count = len(history)

    # 6. Zapisz tylko jeżeli coś się zmieniło.
    if new_count != old_count:

        save_history(
            history
        )

        print(
            "NOWY POMIAR ZAPISANY."
        )

        print(
            f"Liczba rekordów: {new_count}"
        )

    else:

        print(
            "Brak nowych danych — "
            "plik nie został zmieniony."
        )

    print("=" * 60)
    print("ZAKOŃCZONO")
    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        update()

    except requests.RequestException as error:

        print()
        print(
            "BŁĄD POŁĄCZENIA Z IMGW:"
        )
        print(error)

        raise

    except Exception as error:

        print()
        print(
            "BŁĄD:"
        )
        print(error)

        raise
