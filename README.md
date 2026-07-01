# Grafik Pracy — system zarządzania lokalem gastronomicznym

[![CI](https://github.com/oskarolejnik/projekt-aplikacja-grafik/actions/workflows/ci.yml/badge.svg)](https://github.com/oskarolejnik/projekt-aplikacja-grafik/actions/workflows/ci.yml)

**Grafik Pracy** to komercyjny system (SaaS) do prowadzenia restauracji, domu weselnego czy kawiarni:
automatyczne układanie grafików, ewidencja czasu pracy, rozliczenia kasowe, rezerwacje i imprezy oraz
powiadomienia — dostępny jako aplikacja **webowa (PWA)** i **desktopowa (Electron)**.

Produkt jest **white-label** i **konfigurowalny per lokal**: nazwę, logo i moduły ustawia się bez zmian w kodzie,
dzięki czemu ten sam system wdraża się w dowolnej firmie gastronomicznej.

> 🔒 **Oprogramowanie własnościowe (komercyjne).** Wszelkie prawa zastrzeżone — zob. [LICENSE](LICENSE).
> Repozytorium nie jest oprogramowaniem open source; używanie, kopiowanie i wdrażanie wymaga licencji.

---

## ✨ Główne funkcje

- **Grafiki pracy** — automatyczne układanie zmian (algorytm uwzględnia kwalifikacje, dyspozycyjność, urlopy,
  priorytety stanowisk i równy podział zmian) + ręczna edycja i publikacja.
- **Dyspozycyjność i urlopy** — pracownicy zgłaszają dyspozycje i wnioski urlopowe; administrator akceptuje.
- **Ewidencja czasu pracy (RCP)** — godziny liczone wg stawek (raporty godzin/wynagrodzeń); opcjonalna
  synchronizacja z systemem POS przez lokalnego agenta.
- **Rozliczenia kasowe** — rozliczenia dnia (sala) i imprez: gotówka, karty, terminale, kasy, zadatki;
  zeszyt kasowy z saldem.
- **Rezerwacje i imprezy** — kalendarz imprez, import z Google Calendar oraz plików `.ics` i Excel (`.xlsx`).
- **Role i uprawnienia** — administrator, szef, szef kuchni, pracownik obsługi/kuchni, dział techniczny.
- **Powiadomienia Web Push** — np. „raport gotowy", „start zmiany".
- **Konfiguracja lokalu (white-label)** — nazwa, logo, kolor, początek tygodnia i włączone moduły
  ustawiane per instancja (encja `LokalConfig`, endpoint `/api/lokal/config`).

## 🧱 Architektura i technologie

| Warstwa | Technologie |
|---|---|
| **Backend** | Python, FastAPI, SQLAlchemy, Alembic, Uvicorn; JWT (bcrypt), Web Push (VAPID) |
| **Baza danych** | PostgreSQL (produkcja) lub SQLite (dev) — wybór przez `DATABASE_URL` |
| **Frontend** | React 18, Vite, Tailwind CSS, framer-motion, PWA (service worker) |
| **Desktop** | Electron |
| **Agent lokalny** | Python / PowerShell — odczyt z MS SQL Server (POS Gastro/RCP), jednokierunkowy push danych |
| **Migracje / testy** | Alembic, pytest |

Model wdrożenia: **instance-per-tenant** — każdy klient to izolowana instancja (własna baza), hostowana
centralnie. Backend serwuje zbudowany frontend z tego samego adresu (same-origin).

## 📁 Struktura projektu

```
backend/         API (FastAPI), modele, algorytm grafiku, logika rozliczeń, migracje (Alembic), testy
frontend/        Aplikacja React (Vite) + PWA
electron/        Powłoka desktopowa (uruchamia backend i ładuje frontend)
agent_lokalny/   Agent czytający bazę POS/RCP i wysyłający dane na backend
sample_data/     Przykładowe dane
docker-compose.yml   Lokalny PostgreSQL
```

## 🚀 Uruchomienie lokalne

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # uzupełnij sekrety
# Tryb deweloperski (pozwala na domyślne sekrety i lokalny CORS):
#   APP_ENV=development
# Najszybszy start (SQLite) — w .env ustaw:  DATABASE_URL=sqlite:///./scheduler.db

alembic upgrade head          # utwórz/aktualizuj schemat bazy
python create_admin.py        # utworzenie konta administratora
uvicorn main:app --reload --port 8000
```

API wystartuje pod `http://127.0.0.1:8000` (status: `/api/health`).

> 🔐 **Bezpieczeństwo (secure by default).** W trybie produkcyjnym (`APP_ENV` nieustawione lub `production`)
> aplikacja **odmówi startu**, gdy `SECRET_KEY`/`RCP_INGEST_TOKEN` mają wartości domyślne. Wygeneruj sekret:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy /api -> :8000)
# produkcyjnie:
npm run build                 # build trafia do frontend/dist (serwowany przez backend)
```

### 3. PostgreSQL przez Docker (opcjonalnie)

```bash
docker compose up -d
```

### 4. Aplikacja desktopowa (Electron)

```bash
npm install
npm start                     # buduje frontend i uruchamia Electron
```

> Ścieżkę interpretera Pythona ustaw zmienną `GRAFIK_PYTHON` (lub umieść venv w `backend/venv`).

## 🗄️ Migracje bazy (Alembic)

Schemat jest wersjonowany przez Alembic. Najczęstsze komendy (z katalogu `backend/`):

```bash
alembic upgrade head                         # zastosuj migracje (utwórz/zaktualizuj schemat)
alembic revision --autogenerate -m "opis"    # nowa migracja po zmianie models.py (przejrzyj plik!)
alembic check                                # CI: czy modele zgadzają się z migracjami
```

Szczegóły i provisioning nowego klienta: [`backend/migrations/README.md`](backend/migrations/README.md).

## 🏢 Wdrożenie nowego klienta (provisioning)

Model **instance-per-tenant**: każdy klient dostaje izolowaną instancję z własną bazą i sekretami.
Skrypt `backend/new_client.py` przygotowuje nową instancję **jednym poleceniem** — generuje
bezpieczne sekrety, tworzy gotowy do produkcji plik `.env` w `backend/instances/<slug>/`, a z flagą
`--init` od razu inicjuje bazę (Alembic), zakłada administratora i ustawia nazwę lokalu:

```bash
# Z katalogu backend/ (Postgres zaleca się produkcyjnie przez --db-url):
python new_client.py restauracja-pod-lipa --nazwa "Restauracja Pod Lipą" \
    --admin szefowa --domena podlipa.pl --init

# Bez --init skrypt tylko tworzy katalog instancji i .env (bazę inicjujesz później).
# --db-url postgresql+psycopg2://user:haslo@host:5432/grafik_<slug>   # baza produkcyjna
# --haslo "..."   # puste = wygeneruje i wypisze losowe hasło administratora
```

Katalog `instances/` zawiera prawdziwe sekrety i bazy — jest w `.gitignore` i **nigdy nie trafia do repo**.
Następnie uruchom backend ze środowiskiem tej instancji (plik `.env` instancji).

## 🐳 Wdrożenie produkcyjne (Docker + Caddy)

Gotowy stack produkcyjny w `docker-compose.prod.yml`: **aplikacja** (obraz z `Dockerfile` —
backend FastAPI serwujący zbudowany frontend), **PostgreSQL** i **Caddy** jako reverse proxy
z **automatycznym HTTPS** (Let's Encrypt). Obraz jest wielostopniowy: etap 1 buduje frontend (Vite),
etap 2 uruchamia backend serwujący statyki (same-origin). Migracje Alembic wykonują się
automatycznie przy starcie (`init_db()`), więc wdrożenie sprowadza się do:

```bash
cp .env.prod.example .env        # uzupełnij DOMENA, SECRET_KEY, POSTGRES_PASSWORD…
docker compose -f docker-compose.prod.yml up -d --build

# Pierwszy administrator (jednorazowo, po starcie):
docker compose -f docker-compose.prod.yml exec app python create_admin.py
```

DNS domeny musi wskazywać na serwer — Caddy sam pobierze i odnowi certyfikat TLS. Do testów
lokalnych zostaw `DOMENA=localhost` (serwuje po HTTP). Pliki `.env`, bazy i katalog `instances/`
są w `.gitignore` i nie trafiają ani do repo, ani do obrazu (`.dockerignore`).

## 💾 Kopie zapasowe i odtwarzanie

Skrypt [`scripts/backup.sh`](scripts/backup.sh) robi zrzut bazy PostgreSQL (`pg_dump`), kompresuje
go i usuwa kopie starsze niż `RETENCJA_DNI` (domyślnie 14). Działa lokalnie i w kontenerze:

```bash
# Bezpośrednio (host z dostępem do bazy):
DATABASE_URL="postgresql://grafik:haslo@localhost:5432/grafik" ./scripts/backup.sh

# W stacku Docker (profil "backup" — nie startuje z całym stackiem):
docker compose -f docker-compose.prod.yml --profile backup run --rm backup

# Codziennie o 3:00 przez cron hosta:
0 3 * * * cd /sciezka/do/projektu && docker compose -f docker-compose.prod.yml --profile backup run --rm backup
```

Kopie lądują w `./backups/grafik-<data>.sql.gz` (katalog w `.gitignore`). **Odtworzenie:**

```bash
gunzip -c backups/grafik-20260701-030000.sql.gz | psql "postgresql://grafik:haslo@host:5432/grafik"
```

## 🎨 White-label (marka per lokal)

Branding i moduły ustawia administrator przez `PUT /api/lokal/config` (encja `LokalConfig`):
`nazwa_lokalu`, `logo_url`, `kolor_primary`, `poczatek_tygodnia`, flagi `modul_*`. Frontend pobiera
publiczny branding z `GET /api/lokal/branding` i stosuje go w całym interfejsie (bez przebudowy).

## 🔌 Agent lokalny (POS/RCP) — opcjonalny

Katalog `agent_lokalny/` zawiera skrypt (Python lub PowerShell) działający **na komputerze w lokalu**.
Czyta bazę systemu POS (Gastro/RCP) w trybie *tylko do odczytu* i **jednokierunkowo** wypycha dane na backend
(godziny pracy, stan stołów, rozliczenia, zadatki). Backend nigdy nie łączy się z siecią lokalu.
Szczegóły: [`agent_lokalny/README.md`](agent_lokalny/README.md).

## ✅ Testy

```bash
cd backend
pip install -r tests/requirements-test.txt
pytest
```

## 📄 Licencja

Oprogramowanie własnościowe. **Wszelkie prawa zastrzeżone.** Zob. [LICENSE](LICENSE).
W sprawie licencji komercyjnej i wdrożeń: oskarolejnik0@gmail.com.

---

### English summary

**Grafik Pracy** is a commercial (proprietary) management system for restaurants and event venues:
automated staff scheduling, time tracking, cash settlements, reservations/events and Web Push notifications.
Built with **FastAPI + SQLAlchemy + Alembic** (backend, PostgreSQL/SQLite), **React + Vite** (PWA frontend)
and **Electron** (desktop), plus an optional local agent that reads a POS/RCP database (MS SQL Server) and
pushes data to the backend. The product is **white-label** and configured per venue (no code changes).
Deployment model: instance-per-tenant. **All rights reserved** — see [LICENSE](LICENSE).

**Author:** Oskar Olejnik · 2025–2026
