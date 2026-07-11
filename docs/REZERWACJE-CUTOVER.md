# Cutover rezerwacji Google/iCal → Lokalo

Ten runbook przełącza agregaty rezerwacji na kanoniczne `Termin(rodzaj="stolik")` bez trwałego
dual-write. Samo wdrożenie kodu pozostaje w bezpiecznym trybie `legacy`; przełączenie jest decyzją
operatora po raporcie różnic.

## Warunki wejścia

- aktualny backup bazy,
- wdrożona migracja `0050_rezerwacje_source_identity`,
- stały `ENCRYPTION_KEY` (wymagany również przez `--apply`),
- działające konto Google tylko do odczytu albo poprawny eksport `.ics`,
- uzgodnione `--start`, `--end` (koniec wyłączny), jawna data odcięcia oraz
  `--coverage-through` obejmujące cały przyjęty horyzont przyszłych rezerwacji,
- jedno źródło dla jednego kalendarza: nie importuj tych samych wpisów równolegle przez Google i ICS.

W Docker Compose plik Google umieść jako `./secrets/google_sa.json`; kontener widzi go pod
`/run/secrets/lokalo/google_sa.json`. Ustaw też `GOOGLE_CALENDAR_ID`.

## 1. Wdrożenie bez zmiany zachowania

```env
REZERWACJE_READ_MODE=legacy
REZERWACJE_CUTOVER_DATE=
```

Uruchom migracje/start aplikacji i potwierdź, że dotychczasowy agregat nadal działa.

## 2. Raport dry-run

Google:

```powershell
cd backend
python reconcile_rezerwacje.py --source google --start 2026-01-01 --end 2027-01-01 `
  --cutover-date 2026-07-15 --coverage-through 2027-01-01 `
  --report rezerwacje-cutover.json
```

iCal (tylko jawne, niecykliczne VEVENT z godziną i strefą):

```powershell
python reconcile_rezerwacje.py --source ical --ics export.ics --start 2026-01-01 `
  --end 2027-01-01 --cutover-date 2026-07-15 --coverage-through 2027-01-01 `
  --report rezerwacje-cutover.json
```

Raport nie zawiera nazwisk, telefonu, e-maila ani notatek. `issues[]` wskazuje sprawy przez stabilny
anonimowy `ref`, datę/godzinę, liczebność, opcjonalny `termin_id` i nazwy zmienionych pól.

`--coverage-through` jest jawną granicą kompletności źródła (dla zakresu z końcem wyłącznym może
być równe `--end`). Ustal ją co najmniej na koniec całego okna, w którym system legacy przyjmował
rezerwacje — nie wybieraj krótkiej daty tylko po to, aby uzyskać zielony raport. Narzędzie wymaga,
aby granica była późniejsza zarówno od uruchomienia raportu, jak i od daty odcięcia; raport pokazuje
osobno każdy warunek w `coverage`.

Przed zapisem rozwiąż ręcznie `possible_duplicate`, `changed`, `source_missing` i błędy źródła.
`safe_to_cutover=false` oznacza twardą blokadę przełączenia.

## 3. Jednorazowy import czystych braków

Powtórz to samo polecenie z `--apply`. Import obejmuje wyłącznie jednoznaczne
`missing_in_termin`, działa w jednej transakcji i po zapisie generuje świeży raport.

```powershell
python reconcile_rezerwacje.py --source google --start 2026-01-01 --end 2027-01-01 `
  --cutover-date 2026-07-15 --coverage-through 2027-01-01 --apply `
  --report rezerwacje-cutover-after-apply.json
```

Kod wyjścia różny od zera lub `apply.status=error` oznacza brak zatwierdzonego importu. Nie omijaj
tej bramki ręcznym przełączeniem trybu.

## 4. Shadow-read

```env
REZERWACJE_READ_MODE=shadow
REZERWACJE_CUTOVER_DATE=2026-07-15
```

Po restarcie użytkownik nadal widzi legacy, a log `rezerwacje_shadow_delta` pokazuje wyłącznie
anonimowe różnice per data/godzina. `shadow_unavailable` oznacza, że porównanie jest nieważne — nie
traktuj pustego wyniku jako zgodności.

## 5. Finalne odcięcie

1. Zatrzymaj nowe zapisy do Bookero/Google/iCal albo przełącz formularz na Lokalo.
2. Wykonaj ostatni dry-run i `--apply` na tym samym zakresie.
3. Wymagaj `safe_to_cutover=true`, pustej listy przyszłych nierozwiązanych problemów i kodu wyjścia 0.
4. Ustaw datę odcięcia na dzisiaj lub wcześniej i przełącz:

```env
REZERWACJE_READ_MODE=canonical
REZERWACJE_CUTOVER_DATE=2026-07-15
```

5. Po restarcie sprawdź `/api/rezerwacje` jako admin/manager/pracownik oraz
   `/api/me/rezerwacje` jako pracownik. Pełne `/api/rezerwacje-stolik` nadal musi być dla pracownika
   niedostępne.

Tryb `canonical` nigdy nie wraca awaryjnie do Google. Po odcięciu naprawiaj dane kanoniczne i nie
włączaj ponownie trwałego dual-write; fallback ukryłby problem i ponownie utworzył dwa źródła prawdy.
