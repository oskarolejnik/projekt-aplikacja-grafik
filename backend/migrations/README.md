# Migracje bazy danych (Alembic)

Schemat bazy jest wersjonowany przez **Alembic**. Źródłem prawdy o schemacie są modele
SQLAlchemy w `models.py`; migracje w `versions/` opisują, jak doprowadzić bazę do tego stanu.
Zastępuje to dawny ręczny hak `_ensure_schema()` (który dodawał kolumny `ALTER`-ami przy starcie).

> Wszystkie komendy uruchamiaj z katalogu `backend/`, z aktywnym venv i ustawionym
> `DATABASE_URL` (tym samym, którego używa aplikacja).

## Najczęstsze operacje

**Zastosuj wszystkie migracje (utwórz/zaktualizuj schemat):**
```bash
alembic upgrade head
```

**Sprawdź, czy modele zgadzają się z migracjami (CI):**
```bash
alembic check          # kod ≠ 0, jeśli brakuje migracji dla zmian w modelach
```

**Wygeneruj nową migrację po zmianie modeli (`models.py`):**
```bash
alembic revision --autogenerate -m "krótki opis zmiany"
# PRZEJRZYJ wygenerowany plik w versions/ przed commitem!
alembic upgrade head
```

**Historia / bieżąca wersja:**
```bash
alembic history --verbose
alembic current
```

## Automatyka przy starcie aplikacji

`database.init_db()` (wywoływane w starcie FastAPI) jest świadome Alembica i robi „to, co trzeba":

| Stan bazy | Zachowanie |
|---|---|
| Pusta (nowy klient / dev / Electron) | `upgrade head` — buduje pełny schemat z migracji |
| Zarządzana przez Alembica (jest `alembic_version`) | `upgrade head` — stosuje nowe migracje |
| „Legacy" (są tabele, brak `alembic_version`) | domyka kolumny (`_ensure_schema`) i **adoptuje** bazę (`stamp head`), bez odtwarzania danych |

Dzięki temu **istniejące wdrożenie produkcyjne zostaje bezpiecznie przejęte** przez Alembic
przy pierwszym restarcie — bez utraty danych. Jeśli Alembic nie jest zainstalowany, działa
bezpieczny fallback (`create_all` + `_ensure_schema`).

### Adopcja istniejącej bazy ręcznie (alternatywa)
Jeśli wolisz zrobić to świadomie, zamiast polegać na automacie:
```bash
alembic stamp head     # oznacz istniejącą bazę jako bieżącą, bez uruchamiania migracji
```

## Provisioning nowego klienta (model instance-per-tenant)
Dla nowej, pustej bazy:
```bash
export DATABASE_URL=postgresql+psycopg2://<user>:<haslo>@<host>:5432/<baza_klienta>
alembic upgrade head          # zbuduj schemat
python create_admin.py        # utwórz konto administratora klienta
```

## Zasady
- **Nie modyfikuj wygenerowanych migracji po ich wdrożeniu** u jakiegokolwiek klienta — twórz nową.
- **Zawsze przeglądaj** plik z `--autogenerate` (potrafi przeoczyć zmiany typów/nazw).
- Migracje trzymaj w repozytorium (są wersjonowane razem z kodem).
- `alembic check` warto wpiąć do CI, by wymusić migrację przy każdej zmianie modeli.
