# Jeziorsko monitoring

Automatyczne pobieranie dziennych raportów PDF Wód Polskich RZGW Poznań.

Parser nie zakłada stałej nazwy pliku. Wyszukuje raporty `zbiorniki_YYYY-MM-DD`, wybiera najnowszy i dopiero wtedy pobiera PDF.

W razie zmiany HTML strony skrypt wypisuje diagnostykę fragmentów zawierających `zbiorniki`, zamiast kończyć się nieinformacyjnym błędem.
