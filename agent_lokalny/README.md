# Agent RCP (serwer lokalny Gastro LSI → VPS)

Mały, zawsze włączony agent w sieci lokalnej. Czyta odbicia z bazy RCP **tylko do odczytu
(NOLOCK)** i **wypycha** je na VPS. **VPS nigdy nie łączy się do tej sieci** — więc nie może
zaburzyć Gastro LSI. Pliki/baza zostają na lokalu; na VPS idą tylko kopie odbić.

## Wymagania
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
