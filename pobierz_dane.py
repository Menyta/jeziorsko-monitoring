import requests
import json
from datetime import datetime

def fetch_and_update():
    # 1. Pobieranie danych z API IMGW (Stacja Skęczniew / Jeziorsko)
    try:
        response = requests.get("https://imgw.pl")
        data_imgw = response.json()
    except Exception as e:
        print(f"Błąd pobierania danych: {e}")
        return

    current_state = data_imgw.get("currentState", {})
    stan_wody_cm = current_state.get("waterStage", 0)
    odplyw = current_state.get("discharge", 0) if current_state.get("discharge") is not None else 0.0
    
    # 2. Przeliczenia
    rzedna = round(110.00 + (stan_wody_cm / 100), 2)
    pojemnosc = round(29.74 + (stan_wody_cm - 125) * 0.1, 2)
    if pojemnosc < 0: pojemnosc = 0.0
    rezerwa = round(202.8 - pojemnosc, 2)
    doplyw = round(odplyw * 0.95, 2)
    
    date_str = current_state.get("date", "")
    if date_str:
        formatted_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    else:
        formatted_date = datetime.now().strftime("%Y-%m-%d")

    # 3. Odczyt dotychczasowego pliku JSON
    try:
        with open("dane.json", "r", encoding="utf-8") as file:
            baza_danych = json.load(file)
    except:
        baza_danych = []

    # Zabezpieczenie przed dublowaniem rekordów z tego samego dnia
    if any(item['data'] == formatted_date for item in baza_danych):
        print(f"Dane dla daty {formatted_date} już istnieją w pliku JSON. Pomijam.")
        return

    # 4. Przygotowanie nowego obiektu danych
    nowy_wpis = {
        "data": formatted_date,
        "rzedna": rzedna,
        "pojemnosc": pojemnosc,
        "doplyw": doplyw,
        "odplyw": odplyw,
        "rezerwa": rezerwa
    }

    # Wstawiamy nowy wpis na sam początek listy
    baza_danych.insert(0, nowy_wpis)

    # 5. Zapisanie zaktualizowanej bazy z powrotem do pliku dane.json
    with open("dane.json", "w", encoding="utf-8") as file:
        json.dump(baza_danych, file, indent=2, ensure_ascii=False)
        
    print(f"Sukces! Dodano nowy rekord do dane.json dla dnia {formatted_date}")

if __name__ == "__main__":
    fetch_and_update()
