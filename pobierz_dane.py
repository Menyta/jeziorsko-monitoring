import requests
import re
from datetime import datetime

def fetch_and_update():
    # 1. Pobieranie danych z oficjalnego API IMGW (Stacja Skęczniew / Jeziorsko)
    # Pobieramy dane hydrologiczne oraz ogólne parametry stacji zbiornikowej
    try:
        response = requests.get("https://imgw.pl")
        data = response.json()
    except Exception as e:
        print(f"Błąd pobierania danych z IMGW: {e}")
        return

    # Wyciągamy potrzebne wartości
    current_state = data.get("currentState", {})
    
    # Przykładowe mapowanie i przeliczenia (IMGW podaje stan w cm, przeliczamy orientacyjnie na rzędną i pojemność)
    # W prawdziwym wdrożeniu wartości te można idealnie skalibrować z tabelą rzędnych IMGW
    stan_wody_cm = current_state.get("waterStage", 0)
    przeplyw = current_state.get("discharge", 0) if current_state.get("discharge") is not None else 0.0
    
    # Przykładowe wyliczenie rzędnej i pojemności na podstawie stanu wody (tutaj wartości demonstracyjne zbliżone do Twoich)
    rzedna = round(110.00 + (stan_wody_cm / 100), 2)
    pojemnosc = round(29.74 + (stan_wody_cm - 125) * 0.1, 2)
    if pojemnosc < 0: pojemnosc = 0.0
    rezerwa = round(202.8 - pojemnosc, 2)
    
    # Formatowanie daty pomiaru (RRRR-MM-DD)
    date_str = current_state.get("date", "")
    if date_str:
        date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        formatted_date = date_obj.strftime("%Y-%m-%d")
    else:
        formatted_date = datetime.now().strftime("%Y-%m-%d")

    # 2. Odczyt pliku index.html
    with open("index.html", "r", encoding="utf-8") as file:
        html = file.read()

    # Zabezpieczenie przed dublowaniem: jeśli dzisiejsza data już jest w tabeli, przerywamy
    if f"<td>{formatted_date}</td>" in html:
        print(f"Dane dla daty {formatted_date} są już aktualne. Pomijam.")
        return

    # 3. Przygotowanie nowego wiersza HTML
    nowy_wiersz = f"<tr><td>{formatted_date}</td><td>{rzedna:.2f}</td><td>{pojemnosc:.2f}</td><td>{przeplyw:.2f}</td><td>{przeplyw:.2f}</td><td>{rezerwa:.2f}</td></tr>\n"

    # 4. Aktualizacja kafelków na górze strony przy użyciu wyrażeń regularnych (regex)
    html = re.sub(r'<p id="current-pojemnosc">.*?</p>', f'<p id="current-pojemnosc">{pojemnosc:.2f} mln m³</p>', html)
    html = re.sub(r'<p id="current-rzedna">.*?</p>', f'<p id="current-rzedna">{rzedna:.2f} m n.p.m.</p>', html)
    html = re.sub(r'<p id="current-rezerwa">.*?</p>', f'<p id="current-rezerwa">{rezerwa:.2f} mln m³</p>', html)

    # 5. Wstrzyknięcie nowego wiersza na początek tabeli (zaraz po znaczniku DATA_START)
    znacznik_start = "<!-- DATA_START -->\n"
    html = html.replace(znacznik_start, znacznik_start + nowy_wiersz)

    # 6. Zapisanie zmodyfikowanego pliku
    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html)
        
    print(f"Pomyślnie dodano dane za dzień {formatted_date}!")

if __name__ == "__main__":
    fetch_and_update()
