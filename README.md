# Jeziorsko – monitoring

Automatyczny monitoring zbiornika Jeziorsko na podstawie codziennych raportów PDF publikowanych przez Wody Polskie – RZGW Poznań.

## Jak działa

1. GitHub Actions uruchamia skrypt co godzinę.
2. Skrypt pobiera stronę:
   https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6
3. Wyszukuje linki do PDF i rozpoznaje datę z nazwy/linku, np. `zbiorniki_2026-09-10.pdf`.
4. Wybiera najnowszy raport.
5. Pobiera PDF i odczytuje wiersz:
   `Zb. Jeziorsko Warta`
6. Zapisuje dane do `dane.json`.
7. Jeśli raport jest taki sam jak poprzednio, nie tworzy zbędnego commita.
8. GitHub Pages wyświetla dane i wykresy z `dane.json`.

## Aktualny format PDF

Dla Jeziorska skrypt odczytuje:

- rzędna wody [m n.p.m.]
- dobowa zmiana rzędnej [m]
- napełnienie [mln m³]
- dobowa zmiana napełnienia [mln m³]
- średni dobowy dopływ [m³/s]
- średni dobowy odpływ [m³/s]
- aktualna rezerwa powodziowa [mln m³]

## Ważne

Nazwa PDF nie jest wpisana na stałe. Skrypt wyszukuje ją na stronie Wód Polskich i wybiera najnowszą datę, więc zmiana nazwy z `zbiorniki_2026-09-10.pdf` na `zbiorniki_2026-09-11.pdf` nie wymaga zmiany kodu.
