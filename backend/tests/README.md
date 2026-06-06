# Testy backendu — grafik pracowniczy

Kompleksowy zestaw testów integracyjnych / E2E (pytest + factory_boy + Faker) napisany
**pod realny kod** aplikacji (`models.py`, `algorithm.py`, `main.py`), a nie pod generyczny
szablon. Pokrywa 4 cele: dane testowe, stanowiska/kwalifikacje, typy zmian oraz
ograniczenia biznesowe — plus E2E przez API i scenariusze obciążeniowe.

## Uruchomienie

```bash
# z katalogu backend/  (te same zależności co aplikacja + narzędzia testowe)
pip install -r tests/requirements-test.txt
cd tests && python -m pytest            # cały zestaw
python -m pytest -m algorithm           # tylko logika algorytmu
python -m pytest -m e2e                 # tylko E2E/API
python -m pytest -m gap -rx             # luki (xfail) z powodami
```

Wynik referencyjny: **77 passed, 7 xfailed** (xfail = świadomie nieobsłużone wymagania).

## Architektura harnessu (`conftest.py`)

- **Izolowana baza**: SQLite in-memory (`StaticPool`) — jeden silnik współdzielony przez
  aplikację, zależność `get_db` (przez `dependency_overrides`) oraz fabryki. Schemat jest
  odtwarzany **przed każdym testem** (pełna izolacja). Produkcyjny Postgres nie jest dotykany.
- **Uwierzytelnianie**: tokeny JWT generowane w fixturach (`create_access_token`); fixtury
  `admin_client`, `make_employee_client`, `company`.
- **Push wyłączony**: `main.wyslij_push` zamockowane (zero ruchu sieciowego/VAPID).

## Mapa plików → cele

| Plik | Cel | Zakres |
|------|-----|--------|
| `factories.py` | 1, 2 | Fabryki ORM + `build_company()` (15+ osób, profile, kwalifikacje) |
| `test_mock_data.py` | **1** | ≥15 pracowników, rozkład profili (student/etat/manager), dyspozycyjność wg profilu |
| `test_positions_qualifications.py` | **2** | Stanowiska (w tym weekend-only), podkategorie/rewiry, kwalifikacje 1↔wiele |
| `test_shifts.py` | **3** | Zmiany poranne/wieczorne/nocne, niestandardowe godziny, split-shift, konflikty |
| `test_scheduling_constraints.py` | **4** | `auto_assign`: kwalifikacje, dyspozycyjność, 1 zmiana/dzień, weekend-only, balans, niedobory; konwersja imprez→wymagania (system zewnętrzny) |
| `test_constraint_gaps.py` | **4** | Ograniczenia prawne/biznesowe — stan vs oczekiwania (xfail) |
| `test_load_scenarios.py` | obciążenie | Pełne tygodnie, przeciążenie, idempotencja, wydajność (28 dni) |
| `test_e2e_flow.py` | E2E | RBAC, rejestracja/logowanie, pełny przepływ: dyspozycyjność → wymagania → auto-assign → publikacja → grafik pracownika |

## Co aplikacja faktycznie egzekwuje (potwierdzone testami)

`auto_assign` (silnik grafiku) pilnuje: **kwalifikacji**, **dyspozycyjności** (dostępność +
„dostępny od" ≤ start zmiany), **jednej zmiany na pracownika dziennie**, **stanowisk
weekend-only**, **sprawiedliwego podziału** i raportuje **niedobory** personelu. Konwersja
imprez (Excel) → wymagania: start −2h (min. 10:00), 1 pracownik / 15 gości (min. 2 dla sal
R2Piw/R2G).

## ⚠️ Raport QA — luki względem wymagań (testy `gap`/xfail)

Te wymagania **nie są zaimplementowane**. Testy kodują oczekiwane zachowanie i są `xfail`
(nie psują CI). Gdy funkcja powstanie → `XPASS` (sygnał, by zdjąć `xfail`).

1. **Minimalny odpoczynek między zmianami** (np. 11h) — brak (zmiany nie mają godziny końca).
2. **Limit godzin/dni w tygodniu** — brak (można obsadzić wszystkie 7 dni).
3. **Limit godzin w miesiącu** — brak.
4. **Urlopy jako encja/zakres** — brak; obejście (działa): niedostępność dzień po dniu.
5. **Detekcja nakładających się godzin** — brak (brak godziny końca zmiany).
6. **Ręczny przydział `POST /api/przydzialy` nie sprawdza kwalifikacji** — pozwala obsadzić
   niewykwalifikowanego (kontrolę ma tylko `auto_assign`).
7. **Ręczny przydział nie sprawdza dyspozycyjności** — pozwala obsadzić niedostępnego.

**Rekomendacje (priorytetowo):** #6 i #7 (spójność reguł między trybem ręcznym a auto) oraz
#1 (wymóg prawny). Realizacja #1/#2/#3/#5 wymaga dodania **godziny końca zmiany** do modelu
`PrzydzialZmiany` (dziś jest tylko `godz_od`).

## Uwagi modelowe

- „Typ zmiany" (poranna/nocna/split) nie jest osobnym polem — wynika z `godz_od`.
- „Priorytet stanowiska" nie jest osobnym polem — de-facto realizują go flaga `tylko_weekend`
  oraz sortowanie slotów wg trudności obsadzenia (najmniej kandydatów → pierwsze).
- Pracownik **bez** rekordu `Dyspozycja` na dany dzień jest traktowany jako **niedostępny**.
