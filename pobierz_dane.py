#!/usr/bin/env python3
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, timeout=60, retries=4):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            print(f"HTTP próba {attempt}/{retries}: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(attempt * 3)
    raise RuntimeError(f"Nie udało się pobrać {url}: {last}")


def date_from(value):
    m = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", value)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def discover_pdf():
    r = get(SOURCE_PAGE)
    print(f"Strona HTTP: {r.status_code}, URL końcowy: {r.url}")
    print(f"Rozmiar HTML: {len(r.text)} znaków")

    # 1. Najważniejsze: wyciągamy adresy PDF zarówno z HTML, jak i z tekstu.
    soup = BeautifulSoup(r.text, "html.parser")
    candidates = {}

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        label = " ".join(a.get_text(" ", strip=True).split())
        absolute = urljoin(r.url, href)
        blob = f"{label} {href} {absolute}"

        d = date_from(blob)
        if not d:
            continue

        if "zbiorniki" not in blob.lower():
            continue

        # Normalne href, także gdy gov.pl używa ścieżki do załącznika.
        candidates[absolute] = (d, label, absolute)

    # 2. Fallback: strona może mieć nazwę załącznika w treści/JS, ale nie
    #    wystawia jej jako prosty href kończący się .pdf.
    for m in re.finditer(
        r"""(?i)(?:https?:)?//[^"' <>\s]+|/[^"' <>\s]+""",
        r.text,
    ):
        raw = m.group(0)
        if "zbiorniki" not in raw.lower():
            continue
        d = date_from(raw)
        if not d:
            continue
        absolute = urljoin(r.url, raw.replace("\\/", "/"))
        candidates[absolute] = (d, raw, absolute)

    # 3. Awaryjnie szukamy nazwy zbiorniki_YYYY-MM-DD w całym HTML.
    #    Jeśli znajdziemy tylko nazwę, spróbujemy ją zamienić na URL załącznika
    #    przez znalezienie najbliższego href w tym samym fragmencie HTML.
    names = sorted(
        set(re.findall(r"(?i)zbiorniki[_\u200b\u200c\u200d\s-]*(20\d{2}[-_]\d{2}[-_]\d{2})", r.text))
    )
    if names:
        print("Nazwy raportów znalezione w HTML:", names[-10:])

    if not candidates:
        # Diagnostyka, żeby następna zmiana strony nie kończyła się enigmatycznym błędem.
        snippets = []
        for m in re.finditer(r"(?i)zbiorniki", r.text):
            snippets.append(re.sub(r"\s+", " ", r.text[max(0, m.start()-250):m.start()+500]))
            if len(snippets) >= 3:
                break
        print("Nie znaleziono bezpośredniego URL PDF.", file=sys.stderr)
        if snippets:
            print("Fragmenty HTML zawierające 'zbiorniki':", file=sys.stderr)
            for s in snippets:
                print(s, file=sys.stderr)
        raise RuntimeError("Nie znaleziono adresu PDF raportu 'zbiorniki_YYYY-MM-DD'.")

    ordered = sorted(candidates.values(), key=lambda x: x[0], reverse=True)
    date, label, url = ordered[0]
    print(f"Wybrany raport: {date}")
    print(f"Link: {url}")
    print(f"Etykieta: {label}")
    return url


def extract_pdf_text(content):
    temp = Path("_raport.pdf")
    temp.write_bytes(content)
    try:
        reader = PdfReader(str(temp))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return " ".join(text.split())
    finally:
        temp.unlink(missing_ok=True)


def parse(text, pdf_url):
    row = re.search(
        r"Zb\.\s*Jeziorsko\s+Warta\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)",
        text, re.I
    )
    if not row:
        raise RuntimeError("PDF pobrano, ale nie znaleziono wiersza 'Zb. Jeziorsko Warta'.")

    vals = [float(x.replace(",", ".")) for x in row.groups()]

    report = re.search(
        r"z dnia\s+(20\d{2}-\d{2}-\d{2})\s+z godz\.\s+(\d{2}:\d{2})\s+\(UTC\)",
        text, re.I
    )
    if not report:
        raise RuntimeError("Nie znaleziono daty/godziny raportu w PDF.")

    data, godzina = report.groups()

    return {
        "data": data,
        "godzina_utc": godzina,
        "rzedna": vals[0],
        "zmiana_rzednej": vals[1],
        "napelnienie": vals[2],
        "zmiana_napelnienia": vals[3],
        "doplyw": vals[4],
        "odplyw": vals[5],
        "rezerwa": vals[6],
        "zrodlo": "Wody Polskie - RZGW Poznań",
        "pdf": pdf_url,
        "pobrano": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def update(record):
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = []

    key = (record["data"], record["godzina_utc"])
    old = next((x for x in data if (x.get("data"), x.get("godzina_utc")) == key), None)

    fields = [
        "data", "godzina_utc", "rzedna", "zmiana_rzednej",
        "napelnienie", "zmiana_napelnienia", "doplyw",
        "odplyw", "rezerwa", "pdf"
    ]

    if old and all(old.get(k) == record.get(k) for k in fields):
        print("Raport już istnieje i dane się nie zmieniły.")
        return False

    if old:
        record["pobrano"] = old.get("pobrano", record["pobrano"])
        data[data.index(old)] = record
    else:
        data.append(record)

    data.sort(key=lambda x: (x.get("data", ""), x.get("godzina_utc", "")), reverse=True)
    DATA_FILE.write_text(
        json.dumps(data[:MAX_RECORDS], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print("Zapisano:", json.dumps(record, ensure_ascii=False))
    return True


def main():
    try:
        pdf_url = discover_pdf()
        pdf = get(pdf_url, timeout=90)
        print(f"PDF HTTP: {pdf.status_code}, typ: {pdf.headers.get('content-type')}, bajty: {len(pdf.content)}")

        if not pdf.content.startswith(b"%PDF"):
            raise RuntimeError(
                "Adres raportu nie zwrócił PDF. "
                f"Content-Type={pdf.headers.get('content-type')}"
            )

        text = extract_pdf_text(pdf.content)
        print("Tekst PDF:", text[:1500])

        record = parse(text, pdf_url)
        update(record)

    except Exception as e:
        print(f"BŁĄD: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
