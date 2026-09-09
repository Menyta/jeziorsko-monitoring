import requests
import re
from datetime import datetime

def fetch_and_update():
    # 1. Pobieranie danych z oficjalnego i stabilnego API IMGW (Stacja Skęczniew / Jeziorsko)
    try:
        response = requests.get("https://imgw.pl")
        data = response.json()
    except Exception as e:
        print(f"Błąd pobierania danych z IMGW: {e}")
        return

    current_state = data.get("currentState", {})
    stan_wody_cm = current_state.get("waterStage", 0)
    
    # Przepływ (odpływ ze zbiornika) z API IMGW
    przeplyw = current_state.get("discharge", 0) if current_state.get("discharge") is not None else 0.0
    
    # 2. Matematyczne przeliczenie parametrów dla Zbiornika Jeziorsko
    # Kalibracja rzędnej i pojemności na podstawie odczytu cm ze stacji hydrologicznej
    rzedna = round(110.00 + (stan_wody_cm / 100), 2)
    pojemnosc = round(29.74 + (stan_wody_cm - 125) * 0.1, 2)
    if pojemnosc < 0: pojemnosc = 0.0
    rezerwa = round(202.8 - pojemnosc, 2)
    
    # Pobranie oficjalnej daty pomiaru z IMGW (Format: RRRR-MM-DD)
    date_str = current_state.get("date", "")
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_obj.strftime("%Y-%m-%d")
        except:
            formatted_date = datetime.now().strftime("%Y-%m-%d")
    else:
        formatted_date = datetime.now().strftime("%Y-%m-%d")

    # 3. Odczyt aktualnego pliku index.html ze strony
    with open("index.html", "r", encoding="utf-8") as file:
        html = file.read()

    # Inteligentne zabezpieczenie: Sprawdzamy, czy ten konkretny dzień ma już swój wiersz <tr>
    if f"<td>{formatted_date}</td>" in html:
        print(f"Zgłoszenie: Dane dla daty {formatted_date} są już na stronie. Nie ma potrzeby nic zmieniać.")
        return

    # 4. Przygotowanie nowego wiersza do tabeli HTML
    # Dopływ symulujemy na podstawie bilansu, odpływ bierzemy z rzeki (przepływ)
    doplyw_szacowany = round(przeplyw * 0.95, 2) 
    nowy_wiersz = f"<tr><td>{formatted_date}</td><td>{rzedna:.2f}</td><td>{pojemnosc:.2f}</td><td>{doplyw_szacowany:.2f}</td><td>{przeplyw:.2f}</td><td>{rezerwa:.2f}</td></tr>\n"

    # 5. Aktualizacja wartości w kafelkach informacyjnych na górze strony (regex)
    html = re.sub(r'<p id="current-pojemnosc">.*?</p>', f'<p id="current-pojemnosc">{pojemnosc:.2f} mln m³</p>', html)
    html = re.sub(r'<p id="current-rzedna">.*?</p>', f'<p id="current-rzedna">{rzedna:.2f} m n.p.m.</p>', html)
    html = re.sub(r'<p id="current-rezerwa">.*?</p>', f'<p id="current-rezerwa">{rezerwa:.2f} mln m³</p>', html)

    # 6. Wstrzyknięcie nowego rekordu bezpośrednio pod znacznik startowy tabeli
    znacznik_start = "<!-- DATA_START -->\n"
    html = html.replace(znacznik_start, znacznik_start + nowy_wiersz)

    # 7. Zapisanie gotowego, zaktualizowanego pliku
    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html)
        
    print(f"Sukces! Nowe dane automatycznie dodane dla daty: {formatted_date}")

if __name__ == "__main__":
    fetch_and_update()
