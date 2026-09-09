import requests


# ============================================================
# KONFIGURACJA
# ============================================================

API_URL = "https://danepubliczne.imgw.pl/api/data/hydro/"


# ============================================================
# POBIERANIE DANYCH IMGW
# ============================================================

def get_hydro_data():
    """
    Pobiera aktualne dane hydrologiczne z oficjalnego API IMGW.
    """

    print("=" * 80)
    print("JEZIORSKO MONITORING - DIAGNOSTYKA")
    print("=" * 80)
    print()
    print("Pobieranie danych z IMGW...")
    print()

    response = requests.get(
        API_URL,
        timeout=30,
        headers={
            "User-Agent": "Jeziorsko-Monitoring/1.0"
        }
    )

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as error:
        raise RuntimeError(
            "IMGW zwróciło odpowiedź, której "
            "nie można odczytać jako JSON."
        ) from error

    if not isinstance(data, list):
        raise RuntimeError(
            "IMGW zwróciło dane w nieoczekiwanym formacie."
        )

    print(
        f"IMGW zwróciło {len(data)} stacji."
    )
    print()

    return data


# ============================================================
# DIAGNOSTYKA
# ============================================================

def show_warta_stations(data):
    """
    Wyświetla wszystkie stacje IMGW znajdujące się
    na rzece Warcie.
    """

    print("=" * 80)
    print("STACJE IMGW NA RZECE WARTA")
    print("=" * 80)
    print()

    found = []

    for station in data:

        river = str(
            station.get("rzeka") or ""
        ).strip().lower()

        if river != "warta":
            continue

        found.append(station)

        print(
            f"ID: {station.get('id_stacji')}"
        )

        print(
            f"STACJA: {station.get('stacja')}"
        )

        print(
            f"RZEKA: {station.get('rzeka')}"
        )

        print(
            f"LAT: {station.get('lat')}"
        )

        print(
            f"LON: {station.get('lon')}"
        )

        print(
            f"STAN WODY: {station.get('stan_wody')}"
        )

        print(
            f"DATA POMIARU: "
            f"{station.get('stan_wody_data_pomiaru')}"
        )

        print(
            f"RZĘDNA ZERA: "
            f"{station.get('rzedna_zerawodowskazu')}"
        )

        print(
            f"PRZEPŁYW: {station.get('przeplyw')}"
        )

        print(
            f"STAN OSTRZEGAWCZY: "
            f"{station.get('stan_ostrzegawczy')}"
        )

        print(
            f"STAN ALARMOWY: "
            f"{station.get('stan_alarmowy')}"
        )

        print("-" * 80)

    print()

    print("=" * 80)
    print(
        f"LICZBA STACJI NA WARCIE: {len(found)}"
    )
    print("=" * 80)
    print()

    if not found:
        print(
            "UWAGA: API IMGW nie zwróciło żadnej "
            "stacji na rzece Warta."
        )

    return found


# ============================================================
# GŁÓWNA FUNKCJA
# ============================================================

def main():

    try:

        data = get_hydro_data()

        show_warta_stations(data)

        print()
        print("=" * 80)
        print("DIAGNOSTYKA ZAKOŃCZONA")
        print("=" * 80)
        print()
        print(
            "Dane NIE zostały zapisane do dane.json."
        )
        print(
            "To jest celowe — najpierw ustalamy "
            "prawidłową stację Jeziorska."
        )

        # Celowo kończymy kodem 1.
        # Dzięki temu workflow pokaże, że jest to
        # etap diagnostyczny, a nie aktualizacja danych.
        raise SystemExit(1)

    except requests.RequestException as error:

        print()
        print("=" * 80)
        print("BŁĄD POŁĄCZENIA Z IMGW")
        print("=" * 80)
        print()
        print(error)

        raise SystemExit(1)

    except Exception as error:

        print()
        print("=" * 80)
        print("BŁĄD")
        print("=" * 80)
        print()
        print(error)

        raise SystemExit(1)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
