#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys, time
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
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            print(f"HTTP próba {attempt}/{retries}: {exc}", file=sys.stderr)
            if attempt < retries:
                time.sleep(attempt * 3)
    raise RuntimeError(f"Nie udało się pobrać {url}: {last}")

def date_from(value: str):
    match = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", value)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None

def discover_pdf():
    response = get(SOURCE_PAGE)
    print(f"Strona HTTP: {response.status_code}, URL końcowy: {response.url}")
    print(f"Rozmiar HTML: {len(response.text)} znaków")
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        label = " ".join(anchor.get_text(" ", strip=True).split())
        absolute = urljoin(response.url, href)
        blob = f"{label} {href} {absolute}"
        report_date = date_from(blob)
        if report_date and "zbiorniki" in blob.lower():
            candidates[absolute] = (report_date, label, absolute)
    # Fallback for gov.pl attachment links without a .pdf suffix.
    for match in re.finditer(r"""(?i)(?:https?:)?//[^"' <>\s]+|/[^"' <>\s]+""", response.text):
        raw = match.group(0).replace("\\/", "/")
        report_date = date_from(raw)
        if report_date and "zbiorniki" in raw.lower():
            absolute = urljoin(response.url, raw)
            candidates[absolute] = (report_date, raw, absolute)
    if not candidates:
        snippets = []
        for match in re.finditer(r"(?i)zbiorniki", response.text):
            snippets.append(re.sub(r"\s+", " ", response.text[max(0, match.start()-250):match.start()+500]))
            if len(snippets) >= 3:
                break
        print("Nie znaleziono bezpośredniego URL PDF.", file=sys.stderr)
        for snippet in snippets:
            print(snippet, file=sys.stderr)
        raise RuntimeError("Nie znaleziono adresu PDF raportu 'zbiorniki_YYYY-MM-DD'.")
    report_date, label, url = sorted(candidates.values(), key=lambda item: item[0], reverse=True)[0]
    print(f"Wybrany raport: {report_date}")
    print(f"Link: {url}")
    print(f"Etykieta: {label}")
    return url, report_date

def extract_pdf_text(content: bytes):
    temp = Path("_raport.pdf")
    temp.write_bytes(content)
    try:
        reader = PdfReader(str(temp))
        return " ".join(" ".join(page.extract_text() or "" for page in reader.pages).split())
    finally:
        temp.unlink(missing_ok=True)

def parse(text: str, pdf_url: str, filename_date: str):
    row = re.search(
        r"Zb\.\s*Jeziorsko\s+Warta\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)\s+([-+]?\d+(?:[.,]\d+)?)\s+"
        r"([-+]?\d+(?:[.,]\d+)?)",
        text, re.I
    )
    if not row:
        raise RuntimeError("PDF pobrano, ale nie znaleziono wiersza 'Zb. Jeziorsko Warta'.")
    vals = [float(value.replace(",", ".")) for value in row.groups()]
    report = re.search(
        r"z dnia\s+(20\d{2}-\d{2}-\d{2})\s+z godz\.\s+(\d{2}:\d{2})\s+\(UTC\)",
        text, re.I
    )
    if report:
        report_date, report_time = report.groups()
        time_source = "PDF"
    else:
        report_date, report_time = filename_date, ""
        time_source = "nazwa pliku; godzina niepodana"
    print(f"Data raportu: {report_date}; godzina UTC: {report_time or 'niepodana'} (źródło: {time_source})")
    return {
        "data": report_date, "godzina_utc": report_time,
        "rzedna": vals[0], "zmiana_rzednej": vals[1],
        "napelnienie": vals[2], "zmiana_napelnienia": vals[3],
        "doplyw": vals[4], "odplyw": vals[5], "rezerwa": vals[6],
        "zrodlo": "Wody Polskie - RZGW Poznań", "pdf": pdf_url,
        "pobrano": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }

def update(record):
    data = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    if record["godzina_utc"]:
        old = next((item for item in data if item.get("data") == record["data"]
                    and item.get("godzina_utc", "") == record["godzina_utc"]), None)
    else:
        # With no time in the PDF, date alone identifies the daily report.
        old = next((item for item in data if item.get("data") == record["data"]), None)
    fields = ["data", "godzina_utc", "rzedna", "zmiana_rzednej", "napelnienie",
              "zmiana_napelnienia", "doplyw", "odplyw", "rezerwa", "pdf"]
    if old and all(old.get(field, "") == record.get(field, "") for field in fields):
        print("Raport już istnieje i dane się nie zmieniły.")
        return False
    if old:
        record["pobrano"] = old.get("pobrano", record["pobrano"])
        data[data.index(old)] = record
    else:
        data.append(record)
    data.sort(key=lambda item: (item.get("data", ""), item.get("godzina_utc", "")), reverse=True)
    DATA_FILE.write_text(json.dumps(data[:MAX_RECORDS], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Zapisano:", json.dumps(record, ensure_ascii=False))
    return True

def main():
    try:
        pdf_url, report_date = discover_pdf()
        pdf = get(pdf_url, timeout=90)
        print(f"PDF HTTP: {pdf.status_code}, typ: {pdf.headers.get('content-type')}, bajty: {len(pdf.content)}")
        if not pdf.content.startswith(b"%PDF"):
            raise RuntimeError(f"Adres raportu nie zwrócił PDF. Content-Type={pdf.headers.get('content-type')}")
        text = extract_pdf_text(pdf.content)
        print("Tekst PDF:", text[:1500])
        update(parse(text, pdf_url, report_date))
    except Exception as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
