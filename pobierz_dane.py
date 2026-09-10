#!/usr/bin/env python3
"""
Jeziorsko Monitoring
Pobiera najnowszy raport PDF ze strony Wód Polskich RZGW Poznań,
wyszukuje dane dla zbiornika Jeziorsko i aktualizuje dane.json.

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

# Całkowita pojemność Jeziorska podawana w materiałach statystycznych.
# W raporcie Wód Polskich publikowana jest natomiast rezerwa.
TOTAL_CAPACITY_MLN_M3 = 202.8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Jeziorsko-Monitoring/1.0; +https://github.com/Menyta/jeziorsko-monitoring)"
}


def get(url, timeout=60):
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def find_pdf_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        full = urljoin(SOURCE_PAGE, href)

        if ".pdf" in full.lower() or "zbiorniki_" in full.lower():
            links.append((full, text))

    # Usunięcie duplikatów
    unique = []
    seen = set()
    for url, text in links:
        if url not in seen:
            unique.append((url, text))
            seen.add(url)

    return unique


def pdf_date(url, text=""):
    """Wyciąga datę z nazwy PDF lub tekstu linku."""
    source = f"{url} {text}"
    m = re.search(r"(20\d{2})[-_.](\d{2})[-_.](\d{2})", source)
    if m:
        return datetime.strptime("-".join(m.groups()), "%Y-%m-%d").date()

    return datetime.min.date()


def find_latest_pdf():
    response = get(SOURCE_PAGE)
    links = find_pdf_links(response.text)

    # Najpierw preferujemy raporty zbiornikowe.
    reservoir_links = [
        item for item in links
        if "zbiorniki" in f"{item[0]} {item[1]}".lower()
    ]

    candidates = reservoir_links or links

    if not candidates:
        raise RuntimeError(
            "Nie znaleziono żadnego pliku PDF na stronie Wód Polskich."
        )

    candidates.sort(key=lambda x: pdf_date(x[0], x[1]), reverse=True)
    return candidates[0]


def normalize_pdf_text(text):
    # PDF-y potrafią rozdzielać wyrazy wieloma spacjami / znakami nowej linii.
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text


def extract_jeziorsko(pdf_path):
    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = normalize_pdf_text(text)

    # Szukamy fragmentu zaczynającego się od Jeziorska i kończącego
    # przed kolejnym zbiornikiem / kolejnym obszarem RZGW.
    pattern = re.compile(
        r"Na zbiorniku Jeziorsko(?P<section>.*?)(?=Na zbiorniku Poraj|"
        r"Obszar administrowany przez RZGW w Rzeszowie|"
        r"Obszar administrowany przez RZGW w Warszawie|"
        r"\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)

    if not match:
        raise RuntimeError(
            "W PDF nie znaleziono sekcji 'Na zbiorniku Jeziorsko'. "
            "Możliwa zmiana formatu raportu."
        )

    section = "Na zbiorniku Jeziorsko" + match.group("section")

    def number(patterns, label):
        for pattern in patterns:
            m = re.search(pattern, section, re.IGNORECASE | re.DOTALL)
            if m:
                value = m.group(1).replace(" ", "").replace(",", ".")
                try:
                    return float(value)
                except ValueError:
                    pass
        raise RuntimeError(f"Nie udało się odczytać wartości: {label}")

    rzedna = number(
        [
            r"rzędna piętrzenia wynosi\s*([0-9]+[,.][0-9]+)\s*m",
            r"rzędna piętrzenia wynosi\s*([0-9]+[,.][0-9]+)",
        ],
        "rzędna piętrzenia",
    )

    doplyw = number(
        [
            r"dopływ do zbiornika(?: za ostatnie [^,]+)? wynosi\s*([0-9]+[,.][0-9]+)\s*m[³3]\s*/?\s*s",
            r"dopływ do zbiornika[^0-9]{0,80}([0-9]+[,.][0-9]+)\s*m[³3]\s*/?\s*s",
        ],
        "dopływ",
    )

    odplyw = number(
        [
            r"odpływie średnim(?: z ostatniej doby)?\s*([0-9]+[,.][0-9]+)\s*m[³3]\s*/?\s*s",
            r"odpływ średni\s*([0-9]+[,.][0-9]+)\s*m[³3]\s*/?\s*s",
        ],
        "odpływ",
    )

    rezerwa = number(
        [
            r"dysponuje rezerwą\s*([0-9]+[,.][0-9]+)\s*mln",
        ],
        "rezerwa",
    )

    # W raporcie nie ma bezpośrednio bieżącej objętości zbiornika.
    # Jest rezerwa do maksymalnego poziomu piętrzenia. Dlatego wyliczamy
    # wartość orientacyjną jako całkowita pojemność - rezerwa.
    pojemnosc_szacowana = round(
        max(0.0, TOTAL_CAPACITY_MLN_M3 - rezerwa), 2
    )

    return {
        "rzedna": round(rzedna, 2),
        "doplyw": round(doplyw, 2),
        "odplyw": round(odplyw, 2),
        "rezerwa": round(rezerwa, 2),
        "pojemnosc": pojemnosc_szacowana,
        "pojemnosc_typ": "szacowana",
        "pojemnosc_max": TOTAL_CAPACITY_MLN_M3,
        "tekst_zrodlowy": section.strip(),
    }


def load_history():
    if not DATA_FILE.exists():
        return []

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, OSError):
        print("UWAGA: nie udało się odczytać starego dane.json. Tworzę nową historię.")
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

    pdf_date_value = pdf_date(pdf_url, link_text)
    if pdf_date_value == datetime.min.date():
        raise RuntimeError(
            "Nie udało się ustalić daty raportu z nazwy PDF."
        )

    pdf_path = Path("zbiorniki_latest.pdf")
    pdf_response = get(pdf_url)
    pdf_path.write_bytes(pdf_response.content)

    values = extract_jeziorsko(pdf_path)

    record = {
        "data": pdf_date_value.isoformat(),
        "rzedna": values["rzedna"],
        "pojemnosc": values["pojemnosc"],
        "pojemnosc_typ": values["pojemnosc_typ"],
        "pojemnosc_max": values["pojemnosc_max"],
        "doplyw": values["doplyw"],
        "odplyw": values["odplyw"],
        "rezerwa": values["rezerwa"],
        "zrodlo": "Wody Polskie - RZGW Poznań",
        "pdf": pdf_url,
        "pobrano": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    history = load_history()

    # Jeden wpis na raport/dzień. Jeśli raport został poprawiony,
    # zastępujemy stary wpis tym nowszym.
    history = [
        item for item in history
        if item.get("data") != record["data"]
    ]

    history.append(record)
    history.sort(key=lambda item: item.get("data", ""), reverse=True)

    # Chronimy repozytorium przed niekontrolowanym rozrostem.
    history = history[:1000]

    save_history(history)

    # Usuwamy lokalny PDF - nie ma potrzeby zapisywania go w repo.
    try:
        pdf_path.unlink()
    except OSError:
        pass

    print("\nOdczytane dane:")
    for key in ("data", "rzedna", "pojemnosc", "doplyw", "odplyw", "rezerwa"):
        print(f"  {key}: {record[key]}")

    print(f"\nHistoria zawiera {len(history)} wpisów.")
    print("dane.json został zaktualizowany.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBŁĄD: {exc}", file=sys.stderr)
        sys.exit(1)
