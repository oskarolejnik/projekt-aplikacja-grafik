# Agent RCP (serwer lokalny Gastro LSI → VPS)

Mały, zawsze włączony agent w sieci lokalnej. Czyta odbicia z bazy RCP **tylko do odczytu
(NOLOCK)** i **wypycha** je na VPS. **VPS nigdy nie łączy się do tej sieci** — więc nie może
zaburzyć Gastro LSI. Pliki/baza zostają na lokalu; na VPS idą tylko kopie odbić.

## Dwa warianty agenta
- **PowerShell — `agent_rcp.ps1` (ZALECANY, gdy nie wolno instalować Pythona).** Zero instalacji —
  korzysta z wbudowanych w Windows: PowerShell + .NET (`System.Data.SqlClient`, `Invoke-RestMethod`).
  Konfiguracja w `agent_rcp.env`. Runbook na dole („Wariant PowerShell").
- **Python — `agent.py`.** Wymaga Pythona 3.9+ na serwerze. Konfiguracja w `.env`.

Oba robią to samo i mówią do tego samego endpointu na VPS — wybierz jeden.

## Wymagania (wariant Python)
- Konto bazy RCP **TYLKO DO ODCZYTU** (poproś IT Admina). Bez praw zapisu.
- Python 3.9+ na serwerze lokalnym (lub innym zawsze włączonym urządzeniu w LAN).
- Wyjście **HTTPS** z lokalu do VPS (port 443). Żaden port lokalny nie jest otwierany na zewnątrz.

## Instalacja (krok po kroku — sekrety wpisujesz Ty, nie ja)
1. Skopiuj folder `agent_lokalny/` na serwer Gastro LSI.
2. W folderze:
   ```
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt        # Windows
   copy .env.example .env
   ```
3. Wpisz dane do `.env` (read-only RCP, adres VPS, wspólny token). **Nie wysyłaj mi haseł.**
4. Znajdź właściwą tabelę/kolumny RCP:
   ```
   venv\Scripts\python odkryj_schemat.py               # lista tabel
   venv\Scripts\python odkryj_schemat.py NazwaTabeli   # podgląd danych
   ```
   Następnie ułóż `RCP_SQL` w `.env` tak, by zwracał aliasy: `rcp_id, imie_nazwisko, data, wejscie, wyjscie`.
5. Test jednorazowy (zobacz w logu „Wysłano N odbić → VPS"):
   ```
   venv\Scripts\python agent.py
   ```
6. Uruchom jako **usługę** (żeby działało bez zalogowanego użytkownika):
   - **NSSM** (zalecane): `nssm install AgentRCP` → Path: `...\venv\Scripts\python.exe`, Arguments: `...\agent.py`, Startup dir: folder agenta. `nssm start AgentRCP`.
   - lub **Harmonogram zadań**: zadanie „przy starcie systemu", „uruchom niezależnie od zalogowania", akcja `python agent.py`.

## Co musisz ustawić po stronie VPS (robisz to Ty)
W `.env` aplikacji na VPS:
```
RCP_INGEST_TOKEN=ten-sam-dlugi-sekret-co-w-agencie
IMPREZY_PATH=/var/www/staffrajcula/imprezy        # katalog z plikami imprez (jeśli używasz)
VAPID_*                                            # już skonfigurowane (push działa)
```
Po `git pull` + restart backendu VPS sam utworzy tabelę `odbicia_rcp` (nic nie kasuje).

## Bezpieczeństwo (checklista)
- [ ] Konto RCP **read-only** (zero praw zapisu).
- [ ] `RCP_SQL` zawiera `WITH (NOLOCK)` (agent i tak ustawia READ UNCOMMITTED) — brak blokad na Gastro.
- [ ] `OKNO_DNI` małe (1–2) — lekkie zapytania.
- [ ] `.env` tylko na lokalu, poza repo. Token długi i losowy.
- [ ] Połączenie do VPS po **HTTPS**.
- [ ] Agent nie ma żadnej ścieżki przychodzącej z VPS.

## Jak to działa (przepływ)
```
RCP (Gastro) --SELECT NOLOCK co 30s--> agent.py --HTTPS push--> /api/rcp/ingest (VPS)
   VPS: zapis OdbicieRcp -> push do pracownika (start/koniec zmiany) -> zakładka „Godziny"
```
- Nowe wejście → push „Rozpoczęto zmianę".
- Pojawia się wyjście → liczone godziny → push „Zakończono zmianę: +X h".
- Zakładka „Godziny" w aplikacji: miesięczne sumy z podziałem na stanowiska (z opublikowanego grafiku).

## Wariant PowerShell (bez Pythona) — runbook
Nic nie instalujesz. Wszystko jest w Windows.

1. Skopiuj na serwer Gastro pliki `agent_rcp.ps1` i `agent_rcp.env.example` (np. do `C:\agent_rcp\`).
2. Utwórz konfigurację i uzupełnij ją:
   ```
   copy agent_rcp.env.example agent_rcp.env
   notepad agent_rcp.env
   ```
   - `RCP_CONNECTION_STRING` — konto **read-only** (`db_datareader`) na `Gastro`. Instancja nazwana:
     `Server=SERWER\INSTANCJA`; domyślna: `Server=SERWER` lub `Server=SERWER,1433`.
   - `RCP_SQL` — już wpisany (gotowe zmiany z `NGastroCzasPracy`, parametry `@start`/`@end`).
   - `VPS_INGEST_URL`, `RCP_INGEST_TOKEN` — adres VPS i wspólny token (ten sam co na VPS).
   - Token wygeneruj np.: `powershell -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"`.
3. Test ręczny (Ctrl+C po pierwszym „Wysłano N odbić → VPS"; logi w `agent_rcp.log`):
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File C:\agent_rcp\agent_rcp.ps1
   ```
4. Autostart bez zalogowanego użytkownika (wbudowany Harmonogram zadań — `cmd` jako administrator):
   ```
   schtasks /Create /TN "AgentRCP" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\agent_rcp\agent_rcp.ps1" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
   schtasks /Run /TN "AgentRCP"
   ```
   Stop/again: `schtasks /End /TN "AgentRCP"` / `schtasks /Run /TN "AgentRCP"`. Usunięcie: `schtasks /Delete /TN "AgentRCP" /F`.

Bezpieczeństwo jak w checkliście wyżej: konto read-only, `WITH (NOLOCK)`, małe `OKNO_DNI`, `agent_rcp.env`
tylko na lokalu, HTTPS do VPS, brak ścieżki przychodzącej z VPS.
