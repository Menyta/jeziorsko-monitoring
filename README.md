# Jeziorsko Monitoring

Automatyczny monitoring zbiornika Jeziorsko na podstawie raportów PDF
publikowanych przez Wody Polskie, RZGW Poznań.

## Pliki

- `pobierz_dane.py` — wyszukuje najnowszy PDF i wyciąga dane Jeziorska.
- `dane.json` — historia pobranych raportów.
- `index.html` — strona z aktualnymi danymi i wykresami.
- `.github/workflows/auto_update.yml` — automatyczna aktualizacja co godzinę.

## Ważne

Wody Polskie publikują bezpośrednio rezerwę zbiornika, a nie bieżącą
objętość w mln m³. Pole `pojemnosc` jest dlatego wartością szacunkową:
`202,8 - rezerwa`.

Źródło danych:
https://www.gov.pl/web/wody-polskie-poznan/sytuacja-hydrologiczna6
