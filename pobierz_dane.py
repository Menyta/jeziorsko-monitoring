#!/usr/bin/env python3
"""
Pobiera najnowszy dzienny raport PDF Wód Polskich i aktualizuje dane.json.

Źródło:
https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6

Aktualny format raportu:
Zb. Jeziorsko Warta
rzedna, zmiana rzednej, napelnienie, zmiana napelnienia,
doplyw, odplyw, rezerwa
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

SOURCE_PAGE = "https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6"
DATA_FILE = Path("dane.json")
MAX_RECORDS = 1000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; JeziorskoMonitoring/1.0; "
        "+https://menyta.github.io/jeziorsko-monitoring/)"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, *, timeout: int = 45, retries: int = 3) -> requests.Response:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            print(f"Próba {attempt}/{retries} nieudana: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(3 * attempt)
    raise RuntimeError(f"Nie udało się pobrać: {url}") from last_error


def extract_date_from_text(value: str) -> str | None:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", value)
    return match.group(1) if match else None


def find_latest_pdf() -> tuple[str, str]:
    html = get(SOURCE_PAGE).text
    soup = BeautifulSoup(html, "html.parser")

    candidates: list[tuple[str, str, str]] = []

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        text = " ".join(link.get_text(" ", strip=True).split())
        absolute = urljoin(SOURCE_PAGE, href)

        if ".pdf" not in absolute.lower():
            continue

        combined = f"{text} {absolute}"
        date = extract_date_from_text(combined)

        # Preferujemy raporty "zbiorniki_YYYY-MM-DD.pdf".
        priority = 0 if "zbiorniki" in combined.lower() else 1

        if date:
            candidates.append((date, priority, absolute))

    if not candidates:
        raise RuntimeError("Na stronie Wód Polskich nie znaleziono żadnego pliku PDF.")

    # Najpierw data, potem preferencja pliku "zbiorniki".
    candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)

    latest_date, _, latest_url = candidates[0]
    print(f"Najnowszy raport: {latest_date} -> {latest_url}")
    return latest_url, latest_date


def pdf_text(pdf_bytes: bytes) -> str:
    temp_pdf = Path("raport_jeziorsko.pdf")
    temp_pdf.write_bytes(pdf_bytes)
    try:
        reader = PdfReader(str(temp_pdf))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return " ".join(text.split())
    finally:
        temp_pdf.unlink(missing_ok=True)


def parse_report(text: str, pdf_url: str) -> dict:
    # Przykład z aktualnego formatu PDF:
    # Zb. Jeziorsko Warta 118,06 -0,01 71,37 -0,29 14,89 18,25 142,60
    row_match = re.search(
        r"Zb\.\s*Jeziorsko\s+Warta\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)",
        text,
        flags=re.IGNORECASE,
    )

    if not row_match:
        raise RuntimeError(
            "Nie znaleziono w PDF wiersza 'Zb. Jeziorsko Warta'. "
            "Format raportu mógł się zmienić."
        )

    values = [
        float(value.replace(",", "."))
        for value in row_match.groups()
    ]

    report_match = re.search(
        r"z dnia\s+(20\d{2}-\d{2}-\d{2})\s+"
        r"z godz\.\s+(\d{2}:\d{2})\s+\(UTC\)",
        text,
        flags=re.IGNORECASE,
    )

    if not report_match:
        raise RuntimeError(
            "Nie znaleziono daty/godziny raportu w PDF "
            "(oczekiwany zapis: 'z dnia YYYY-MM-DD z godz. HH:MM (UTC)')."
        )

    data, godzina_utc = report_match.groups()

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return {
        "data": data,
        "godzina_utc": godzina_utc,
        "rzedna": values[0],
        "zmiana_rzednej": values[1],
        "napelnienie": values[2],
        "zmiana_napelnienia": values[3],
        "doplyw": values[4],
        "odplyw": values[5],
        "rezerwa": values[6],
        "zrodlo": "Wody Polskie - RZGW Poznań",
        "pdf": pdf_url,
        "pobrano": now,
    }


def load_data() -> list[dict]:
    if not DATA_FILE.exists():
        return []

    try:
        value = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Nieprawidłowy JSON w {DATA_FILE}: {exc}") from exc

    if not isinstance(value, list):
        raise RuntimeError(f"{DATA_FILE} musi zawierać tablicę JSON.")

    return value


def same_measurement(a: dict, b: dict) -> bool:
    fields = (
        "data",
        "godzina_utc",
        "rzedna",
        "zmiana_rzednej",
        "napelnienie",
        "zmiana_napelnienia",
        "doplyw",
        "odplyw",
        "rezerwa",
        "pdf",
    )
    return all(a.get(field) == b.get(field) for field in fields)


def save_if_changed(record: dict) -> bool:
    data = load_data()

    key = (record["data"], record["godzina_utc"])
    existing_index = next(
        (
            index
            for index, item in enumerate(data)
            if (item.get("data"), item.get("godzina_utc")) == key
        ),
        None,
    )

    if existing_index is not None and same_measurement(data[existing_index], record):
        print("Ten raport jest już zapisany. Brak zmian w dane.json.")
        return False

    if existing_index is not None:
        # Zachowujemy istniejący czas pierwszego pobrania.
        record["pobrano"] = data[existing_index].get("pobrano", record["pobrano"])
        data[existing_index] = record
    else:
        data.append(record)

    data.sort(key=lambda item: (item.get("data", ""), item.get("godzina_utc", "")), reverse=True)
    data = data[:MAX_RECORDS]

    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Zapisano raport {record['data']} {record['godzina_utc']} UTC.")
    return True


def main() -> int:
    try:
        pdf_url, _ = find_latest_pdf()
        pdf_response = get(pdf_url)
        text = pdf_text(pdf_response.content)

        # Przydatne diagnostycznie, jeśli format PDF zmieni się w przyszłości.
        print("Wyciągnięto tekst z PDF.")
        record = parse_report(text, pdf_url)

        print(json.dumps(record, ensure_ascii=False, indent=2))
        save_if_changed(record)
        return 0

    except Exception as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
