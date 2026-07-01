# Aplikacja desktopowa — Lokalo

Wersja desktopowa to powłoka **Electron**, która uruchamia lokalny serwer aplikacji (FastAPI)
i pokazuje interfejs w oknie. Cały produkt (API + frontend) działa na komputerze użytkownika;
baza to lokalny plik SQLite w katalogu danych użytkownika.

Instalator (Windows, NSIS) pakuje **spakowany backend** (PyInstaller → `grafik-backend.exe`),
dzięki czemu na komputerze klienta **nie trzeba instalować Pythona**.

## Budowanie instalatora (Windows)

Wymagania: Node 20/22, Python 3.9+ (do zbudowania backendu; skrypt sam wykryje wersję), npm.

```powershell
# w katalogu głównym repozytorium
.\build-desktop.ps1
```

Skrypt wykonuje trzy kroki:

1. **Frontend** — `npm --prefix frontend run build` → `frontend/dist`
2. **Backend** — PyInstaller pakuje serwer do `backend/dist/grafik-backend/grafik-backend.exe`
   (tworzy własny venv `backend/.venv-build` z zależnościami produkcyjnymi + PyInstaller)
3. **Instalator** — electron-builder (NSIS) → **`electron/dist-installer/Lokalo-Setup-<wersja>.exe`**

Gotowy plik `Lokalo-Setup-<wersja>.exe` to instalator do rozdania — dwuklik, wybór katalogu,
skróty na pulpicie i w menu Start.

## Jak to działa

- `electron/main.js` przy starcie:
  - przygotowuje **katalog danych** (`%APPDATA%\Lokalo\dane`) — tam trafia baza `grafik.db`
    oraz jednorazowo wygenerowane sekrety (`sekrety.json`: `SECRET_KEY`, `RCP_INGEST_TOKEN`);
  - uruchamia backend (spakowany `grafik-backend.exe`, a w trybie dev — `uvicorn` przez Pythona),
    przekazując przez środowisko `DATABASE_URL` (SQLite w katalogu danych), `SECRET_KEY`,
    `FRONTEND_DIST` (statyki serwuje backend) i port (domyślnie `8799`, wewnętrzny);
  - czeka aż `/api/health` odpowie 200 i otwiera okno na `http://127.0.0.1:<port>`;
  - zamyka proces backendu przy wyjściu; pilnuje pojedynczej instancji.
- Schemat bazy tworzy/aktualizuje `init_db()` (Alembic `upgrade head`; migracje są dołączone do
  bundla). Przy aktualizacji aplikacji nowe migracje zastosują się do istniejącej bazy klienta.

## Tryb deweloperski (bez instalatora)

Z Pythonem i zależnościami backendu w venv (`backend/.venv-test` lub własny):

```powershell
# okno na zbudowanym froncie serwowanym przez backend:
npm --prefix frontend run build
npm --prefix electron install
npm --prefix electron start

# albo z hot-reloadem Vite (osobno uruchom 'npm --prefix frontend run dev'):
npm --prefix electron run dev        # ładuje http://localhost:5173
```

W trybie dev `main.js` sam znajdzie Pythona z `backend/.venv-test` / `backend/venv`, albo
użyje interpretera z `PATH`. Można wskazać własny: `set GRAFIK_PYTHON=...python.exe`.

## Ikona

Ikona marki **Lokalo** jest już w repo: `electron/assets/icon.ico` (multi-res 16–256 px,
generowana z `frontend/public/icon.svg`). electron-builder używa jej jako ikony aplikacji,
okna i instalatora. Aby ją odświeżyć po zmianie znaku, przegeneruj z `icon.svg`.

## Rozwiązywanie problemów

**Build instalatora pada na `winCodeSign` — „Cannot create symbolic link ... Klient nie ma
wymaganych uprawnień".** electron-builder rozpakowuje paczkę `winCodeSign` (do podpisywania kodu),
która zawiera macOS-owe dowiązania symboliczne — a Windows nie tworzy ich bez uprawnień
administratora / Trybu dewelopera. Dla niepodpisanego instalatora te pliki są zbędne. Obejścia:

- **Najprościej:** włącz *Tryb dewelopera* (Ustawienia → Prywatność i zabezpieczenia →
  Dla deweloperów → Tryb dewelopera: WŁ.), albo uruchom build w terminalu „jako administrator".
- **Bez zmian systemowych:** rozpakuj `winCodeSign` ręcznie, pomijając katalog `darwin`, tak by
  electron-builder znalazł gotowy cache (`%LOCALAPPDATA%\electron-builder\Cache\winCodeSign\winCodeSign-2.6.0`):

  ```powershell
  $cache = "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign"
  $z = "electron\node_modules\7zip-bin\win\x64\7za.exe"
  # (paczka .7z zostaje w $cache po pierwszej nieudanej próbie builda)
  & $z x "$cache\<nazwa>.7z" "-o$cache\winCodeSign-2.6.0" "-xr!darwin" -y
  ```

  Potem ponów `npm --prefix electron run dist`.

## Uwagi

- Port `8799` jest wewnętrzny (frontend woła `/api` względnie). Zmienisz go zmienną `GRAFIK_PORT`.
- Instalator jest **per-user** (bez uprawnień administratora), z możliwością zmiany katalogu.
- Jeśli PyInstaller nie wychwyci jakiegoś modułu, dodaj go do `hiddenimports` w
  `backend/grafik-backend.spec`.
