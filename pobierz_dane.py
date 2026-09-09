import requests
import json
from datetime import datetime

# 1. Pobranie danych dla stacji Skęczniew (Warta poniżej Jeziorska) z API IMGW
url = "https://imgw.pl"
response = requests.get(url)
data = response.json()

# 2. Wyciągnięcie aktualnego stanu wody i przepływu
odczyt = data.get("currentState", {})
stan_wody = odczyt.get("waterStage", 0)  # w cm
przeplyw = odczyt.get("discharge", 0)     # w m3/s
data_pomiaru = datetime.strptime(odczyt.get("date"), "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")

# 3. Otwarcie Twojego pliku HTML i dopisanie danych do wykresu
with open("index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Tutaj skrypt lokalizuje miejsce w kodzie i dopisuje nowy rekord
# (Wymaga dopasowania do dokładnej struktury Twojego pliku index.html)
print(f"Pobrano dane z dnia {data_pomiaru}: Stan: {stan_wody}cm, Przepływ: {przeplyw}m3/s")
