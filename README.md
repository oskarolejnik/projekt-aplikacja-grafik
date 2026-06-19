# Grafik Pracy — system zarządzania pracą lokalu gastronomicznego

Autorski, full-stackowy system wspierający codzienną pracę restauracji / domu weselnego: automatyczne układanie grafików pracy, ewidencja czasu pracy, rozliczenia kasowe, rezerwacje, imprezy i powiadomienia. Dostępny jako aplikacja **webowa (PWA)** oraz **desktopowa (Electron)**.

> ℹ️ **Jak powstał projekt:** zbudowany w modelu *AI-assisted* — większość kodu wygenerował asystent AI. Moją rolą było zaprojektowanie rozwiązania, określenie wymagań, integracja komponentów, testowanie i uruchomienie całości. Projekt rozwiązuje realny problem operacyjny lokalu, którym zarządzałem.

---

## ✨ Główne funkcje

- **Grafiki pracy** — automatyczne układanie zmian (algorytm uwzględnia kwalifikacje, dyspozycyjność, urlopy, priorytety stanowisk i równy podział zmian) + ręczna edycja i publikacja grafiku.
- **Dyspozycyjność i urlopy** — pracownicy zgłaszają dyspozycje oraz wnioski urlopowe; admin akceptuje.
- **Ewidencja czasu pracy (RCP)** — godziny synchronizowane z systemem POS i liczone wg stawek (raporty godzin/wynagrodzeń).
- **Rozliczenia** — rozliczenia dnia (sala) i imprez: gotówka, karty, terminale, kasy, zadatki; zeszyt kasowy z saldem.
- **Rezerwacje i imprezy** — import z Google Calendar oraz plików `.ics` i Excel (`.xlsx`).
- **Role i uprawnienia** — admin, szef, szef kuchni, pracownik obsługi/kuchni, dział techniczny (sprzątanie, zamówienia).
- **Powiadomienia Web Push** — np. „raport gotowy", „start zmiany".

## 🧱 Architektura i technologie

| Warstwa | Technologie |
|---|---|
| **Backend** | Python, FastAPI, SQLAlchemy, Uvicorn; JWT (bcrypt), Web Push (VAPID) |
| **Baza danych** | PostgreSQL (produkcja) lub SQLite (dev) — wybór przez `DATABASE_URL` |
| **Frontend** | React 18, Vite, Tailwind CSS, framer-motion, PWA (service worker) |
| **Desktop** | Electron |
| **Agent lokalny** | Python / PowerShell — odczyt z MS SQL Server (Gastro/RCP), wypychanie danych na backend |
| **Inne** | Docker (PostgreSQL), pytest (testy) |

## 📁 Struktura projektu

```
backend/         API (FastAPI), modele, algorytm grafiku, logika rozliczeń, testy
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

cp .env.example .env          # uzupełnij SECRET_KEY itd.
# Najszybszy start (SQLite) — w .env ustaw:
#   DATABASE_URL=sqlite:///./scheduler.db
# Albo PostgreSQL przez Dockera (patrz niżej).

python create_admin.py        # utworzenie konta administratora
uvicorn main:app --reload --port 8000
```

API wystartuje pod `http://127.0.0.1:8000` (status: `/api/health`).

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
docker compose up -d          # PostgreSQL zgodny z domyślnym DATABASE_URL
```

### 4. Aplikacja desktopowa (Electron)

```bash
npm install
npm start                     # buduje frontend i uruchamia Electron
```

> Uwaga: w `electron/main.js` ścieżka do interpretera Pythona jest ustawiona na sztywno — dostosuj ją do swojego systemu.

## 🔌 Agent lokalny (POS/RCP)

Katalog `agent_lokalny/` zawiera skrypt (Python lub PowerShell) działający **na komputerze w lokalu**. Czyta bazę systemu POS (Gastro/RCP) w trybie *tylko do odczytu* i **jednokierunkowo** wypycha dane na backend (godziny pracy, stan stołów, rozliczenia, zadatki). Backend nigdy nie łączy się z siecią lokalu. Konfiguracja w `agent_lokalny/.env.example` / `agent_rcp.env.example`. Szczegóły: [`agent_lokalny/README.md`](agent_lokalny/README.md).

## ✅ Testy

```bash
cd backend
pip install -r tests/requirements-test.txt
pytest
```

## 📄 Licencja / status

Projekt prywatny, niekomercyjny — zbudowany na potrzeby konkretnego lokalu (Karczma Rajcula). Repozytorium ma charakter portfolio.

---

### English summary

**Grafik Pracy** ("Work Scheduler") is a full-stack system for running a restaurant / event venue: automated staff scheduling, time tracking, cash settlements, reservations and Web Push notifications. Built with **FastAPI + SQLAlchemy** (backend, PostgreSQL/SQLite), **React + Vite** (PWA frontend) and **Electron** (desktop), plus a local agent that reads a POS/RCP database (MS SQL Server) and pushes data to the backend. The project was built with AI assistance — I owned the design, requirements, integration, testing and deployment.

**Author:** Oskar Olejnik · 2025–2026
