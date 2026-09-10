#!/usr/bin/env python3
"""
Jeziorsko Monitoring
Parser aktualnego formatu PDF Wód Polskich RZGW Poznań.

Aktualny raport (10.09.2026) ma tabelę:
Zbiornik | Rzeka | Rzędna wody górnej | Zmiana dobowa rzędnej |
Napełnienie | Zmiana dobowa napełnienia | Dopływ średni dobowy |
Odpływ średni dobowy | Aktualna rezerwa powodziowa

Przykładowy wiersz z raportu:
Zb. Jeziorsko Warta 118,06 -0,01 71,37 -0,29 14,89 18,25 142,60

Źródło:
https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


SOURCE_PAGE = "https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6"
DATA_FILE = Path("dane.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Jeziorsko-Monitoring/1.0; "
        "+https://github.com/Menyta/jeziorsko-monitoring)"
    )
}


def get(url, timeout=60):
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def normalize(text):
    """Normalizuje tekst wyciągnięty z PDF."""
    text = text.replace("\xa0", " ")
    text = text.replace("\u2212", "-")
    text = re.sub(r"[ \t\r\n]+", " ", text)
    return text.strip()


def extract_date_from_text(text):
    """
    Aktualny PDF zawiera na końcu:
    ... z dnia 2026-09-10 z godz. 05:00 (UTC)
    """
    match = re.search(
        r"z dnia\s+(20\d{2}-\d{2}-\d{2})\s+z godz\.\s+"
        r"(\d{2}:\d{2})\s*\(UTC\)",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1), match.group(2)

    return None, None


def find_pdf_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        full_url = urljoin(SOURCE_PAGE, href)

        if ".pdf" in full_url.lower() or "zbiorniki_" in full_url.lower():
            links.append((full_url, text))

    unique = []
    seen = set()

    for url, text in links:
        if url not in seen:
            unique.append((url, text))
            seen.add(url)

    return unique


def date_from_filename(url, link_text=""):
    source = f"{url} {link_text}"

    match = re.search(
        r"(20\d{2})[-_.](\d{2})[-_.](\d{2})",
        source,
    )

    if match:
        return "-".join(match.groups())

    return None


def find_latest_pdf():
    response = get(SOURCE_PAGE)
    links = find_pdf_links(response.text)

    if not links:
        raise RuntimeError(
            "Nie znaleziono plików PDF na stronie Wód Polskich."
        )

    # Raporty zbiorników mają w nazwie "zbiorniki".
    reservoir_links = [
        item for item in links
        if "zbiorniki" in f"{item[0]} {item[1]}".lower()
    ]

    candidates = reservoir_links or links

    dated = []
    for url, text in candidates:
        d = date_from_filename(url, text)
        if d:
            dated.append((d, url, text))

    if not dated:
        # Jeśli nazwa pliku się zmieni, używamy pierwszego znalezionego PDF.
        return candidates[0][0], candidates[0][1]

    dated.sort(reverse=True)
    return dated[0][1], dated[0][2]


def parse_jeziorsko(pdf_text):
    """
    Parsuje aktualny wiersz tabeli.

    Aktualny format:
    Zb. Jeziorsko Warta
    118,06 -0,01 71,37 -0,29 14,89 18,25 142,60

    Odpowiada to:
    1. rzędna
    2. zmiana dobowa rzędnej
    3. napełnienie
    4. zmiana dobowa napełnienia
    5. dopływ
    6. odpływ
    7. rezerwa powodziowa
    """

    text = normalize(pdf_text)

    # Bierzemy wszystko od "Zb. Jeziorsko Warta" do następnego zbiornika
    # albo do końca dokumentu.
    match = re.search(
        r"Zb\.\s*Jeziorsko\s+Warta\s+"
        r"(?P<values>.*?)(?=\s+Zb\.\s+Poraj\s+Warta|\s+Zestawienie|\Z)",
        text,
        re.IGNORECASE,
    )

    if not match:
        raise RuntimeError(
            "Nie znaleziono w PDF wiersza 'Zb. Jeziorsko Warta'. "
            "Sprawdź, czy Wody Polskie nie zmieniły formatu tabeli."
        )

    values_text = match.group("values")

    numbers = re.findall(
        r"[-+]?\d+(?:[,.]\d+)?",
        values_text,
    )

    if len(numbers) < 7:
        raise RuntimeError(
            "Wiersz Jeziorska został znaleziony, ale zawiera mniej niż "
            f"7 wartości liczbowych: {values_text!r}"
        )

    def f(value):
        return float(value.replace(",", "."))

    values = [f(x) for x in numbers[:7]]

    (
        rzedna,
        zmiana_rzednej,
        napelnienie,
        zmiana_napelnienia,
        doplyw,
        odplyw,
        rezerwa,
    ) = values

    return {
        "rzedna": rzedna,
        "zmiana_rzednej": zmiana_rzednej,
        "napelnienie": napelnienie,
        "zmiana_napelnienia": zmiana_napelnienia,
        "doplyw": doplyw,
        "odplyw": odplyw,
        "rezerwa": rezerwa,
    }


def load_history():
    if not DATA_FILE.exists():
        return []

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except (OSError, json.JSONDecodeError):
        print("UWAGA: istniejący dane.json jest niepoprawny. Tworzę nową historię.")

    return []


def save_history(history):
    DATA_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    print("=" * 70)
    print("JEZIORSKO MONITORING - WODY POLSKIE")
    print("=" * 70)

    pdf_url, link_text = find_latest_pdf()
    print(f"Najnowszy PDF: {pdf_url}")

    pdf_path = Path("zbiorniki_latest.pdf")

    response = get(pdf_url)
    pdf_path.write_bytes(response.content)

    reader = PdfReader(str(pdf_path))
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    report_date, report_time = extract_date_from_text(pdf_text)

    if not report_date:
        report_date = date_from_filename(pdf_url, link_text)

    if not report_date:
        raise RuntimeError(
            "Nie udało się ustalić daty raportu."
        )

    if not report_time:
        report_time = "05:00"

    values = parse_jeziorsko(pdf_text)

    record = {
        "data": report_date,
        "godzina_utc": report_time,
        "rzedna": values["rzedna"],
        "zmiana_rzednej": values["zmiana_rzednej"],
        "napelnienie": values["napelnienie"],
        "zmiana_napelnienia": values["zmiana_napelnienia"],
        "doplyw": values["doplyw"],
        "odplyw": values["odplyw"],
        "rezerwa": values["rezerwa"],
        "zrodlo": "Wody Polskie - RZGW Poznań",
        "pdf": pdf_url,
        "pobrano": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    history = load_history()

    # Jeden wpis dla danego raportu. Jeśli raport zostanie poprawiony,
    # nowsze wykonanie zastąpi poprzedni wpis.
    history = [
        item
        for item in history
        if not (
            item.get("data") == record["data"]
            and item.get("godzina_utc") == record["godzina_utc"]
        )
    ]

    history.append(record)
    history.sort(
        key=lambda item: (
            str(item.get("data", "")),
            str(item.get("godzina_utc", "")),
        ),
        reverse=True,
    )

    history = history[:1000]
    save_history(history)

    try:
        pdf_path.unlink()
    except OSError:
        pass

    print("\nOdczytane dane Jeziorska:")
    print(f"  Data:                    {record['data']}")
    print(f"  Godzina UTC:             {record['godzina_utc']}")
    print(f"  Rzędna:                  {record['rzedna']:.2f} m n.p.m.")
    print(f"  Zmiana dobowa rzędnej:   {record['zmiana_rzednej']:.2f} m")
    print(f"  Napełnienie:             {record['napelnienie']:.2f} mln m3")
    print(f"  Zmiana dobowa napełn.:   {record['zmiana_napelnienia']:.2f} mln m3")
    print(f"  Dopływ:                  {record['doplyw']:.2f} m3/s")
    print(f"  Odpływ:                  {record['odplyw']:.2f} m3/s")
    print(f"  Rezerwa powodziowa:      {record['rezerwa']:.2f} mln m3")
    print(f"\nHistoria: {len(history)} wpisów")
    print("dane.json został zaktualizowany.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBŁĄD: {exc}", file=sys.stderr)
        sys.exit(1)
