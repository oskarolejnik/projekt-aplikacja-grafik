# Integracja Lokalo z systemami POS — research i architektura

*Stan researchu: lipiec 2026. Ten dokument to plan produktowy dla „wtyczki POS dla każdego lokalu" —
uniwersalnego następcy dzisiejszego `agent_lokalny/` (który obsługuje wyłącznie Gastro/NGastro na MSSQL).*

**Stan wdrożenia:** ✅ tor A (utarg ręczny/CSV + `POST /api/pos/utarg-dnia` + heartbeat + zakładka
„Utarg (POS)"), ✅ token agenta z panelu (hash w DB, unieważnialny; env `RCP_INGEST_TOKEN` = fallback,
przyjmowany też na legacy `/api/rcp|gastro/*`), ✅ agent `core+drivers` z driverami **`gastro_mssql`,
`soga_firebird`, `x2_postgres`** (wspólna baza `SqlDriver` — nowy POS = kilka linijek;
`agent_lokalny/agent_pos.py`, config.yaml z panelu) i kreatorem „Podłącz agenta", ✅ **trwałe mapowanie
pracowników POS→Lokalo** (`PracownikPosId`, `pos_pracownik_id` w odbiciach → ingest woli mapę jawną,
fallback = imię; krok mapowań w kreatorze domyka historyczne odbicia).
Do zrobienia: konektor chmurowy Dotykačka (OAuth+webhooki), KSeF (04.2026, B2B/koszty), kolejka offline
+ auto-update agenta, mapowanie rewirów w kreatorze (backend `pos_mapa_rewirow` gotowy).

## 1. Mapa rynku POS w Polsce (2025/2026)

Rynek dzieli się na dwa światy o zupełnie różnych metodach integracji:

**Legacy on-premise (lokalna baza danych, brak API)** — wciąż większość klasycznych restauracji:

| System | Baza lokalna | Jak się zintegrować | Segment |
|---|---|---|---|
| **Gastro Szef / Gastro POS** (Softech → LSI) | **MS SQL** (instancja `(local)\gastro`) | lokalny agent czytający SQL (tak działa dzisiejszy agent Lokalo); eksporty xls/txt/dbf/xml jako fallback | największa baza legacy: ~4,5 tys. lokali |
| **SOGA** (NSoft, dystrybucja Novitus) | **Firebird** (open source, łatwy odczyt) | lokalny agent, driver Firebird | mała gastro, pizzerie, bary (sieć dealerów Novitus) |
| **X2System** (Adith) | **PostgreSQL** | lokalny agent, driver Postgres | 3000+ lokali, także sieci |
| **S4H Chef** | **MS SQL** | lokalny agent (ten sam driver co Gastro) | hotele + gastro hotelowa |
| **LSI POSitive** | MSSQL / chmura | integracje partnerskie przez LSI | sieci, casual dining |

**Nowa fala cloud (publiczne API / webhooki)**:

| System | API | Uwagi |
|---|---|---|
| **Dotykačka** | REST API 2.0 + webhooki, **w każdej licencji, bez negocjacji** — docs.api.dotypos.com | encje Employee / Attendance / Order wprost pasują do domeny Lokalo; ~30 tys. klientów CEE |
| **GoPOS** | API partnerskie (po umowie) | nowoczesna gastro, QSR, sieci |
| **POSbistro** | tylko program partnerski (bez publicznych docs) | mała/średnia mobilna gastro |
| Storyous (Teya) | publiczne API, ale **polska spółka w likwidacji** | pomijalny w PL |
| Square / Lightspeed / Toast | świetne API, **brak fiskalizacji w PL** | pomijalne |

**Warstwa horyzontalna — KSeF 2.0** (obowiązkowy: 1.02.2026 więksi, 1.04.2026 reszta):
publiczne API + schema FA(3). **Uwaga:** paragony B2C *nie* trafiają do KSeF — KSeF jest źródłem danych
o sprzedaży **fakturowej B2B** (imprezy, catering, faktury firmowe) i o **kosztach** (faktury zakupowe →
food cost). Nie zastąpi dziennego utargu paragonowego, ale jest w 100% niezależny od POS-a.

## 2. Architektura docelowa: rdzeń + drivery

```
agent_lokalny/
  core/
    runner.py        # pętla poll, kursor "since", retry z backoffem
    uploader.py      # HTTP push do chmury, kolejka offline (SQLite), dedup po id
    heartbeat.py     # telemetria: wersja, driver, capabilities, błędy
    config.py        # config.yaml (wygenerowany przez panel)
    updater.py       # auto-update (faza 2 — obowiązkowy przed ~10. instalacją)
  drivers/
    base.py          # interfejs PosDriver (Protocol)
    gastro_mssql.py  # dzisiejszy agent.py przeniesiony pod interfejs
    soga_firebird.py # faza 2
    x2_postgres.py   # faza 2 (S4H = wariant gastro_mssql)
```

Interfejs drivera — **jedyna metoda obowiązkowa to dzienny utarg** (lekcja z 7shifts/Planday:
agregat dzienny wystarcza do labor% i prognoz; reszta to `capabilities` włączane per lokal):

```python
class PosDriver(Protocol):
    driver_id: str                # "gastro_mssql"
    capabilities: set[str]        # podzbiór: utarg, odbicia, rozliczenia, storna, stoly, zadatki
    def test_connection(self) -> Status: ...
    def fetch_utarg_dnia(self, since: date) -> list[dict]   # WYMAGANE
    # pozostałe fetch_* opcjonalne wg capabilities
```

Driver mapuje POS-owe formy płatności na kanoniczny enum (`gotowka|karta|przelew|inne`) — po stronie
drivera, nie backendu. SQL-e per moduł zostają w configu drivera (jak dziś `RCP_SQL`), więc różnice
wersji POS-a nie wymagają nowego wydania agenta.

## 3. Kolejność wdrożenia (tory)

1. **Tor A — utarg ręczny/CSV (dni pracy, zero utrzymania).** To nie jest agent: formularz „utarg dnia"
   + import CSV w panelu, piszące w ten sam endpoint `POST /api/pos/utarg-dnia`, co przyszłe agenty.
   100% pokrycia rynku od pierwszego dnia i wspólny model danych dla wszystkiego dalej.
2. **Driver `gastro_mssql`** — przeniesienie istniejącego `agent.py` pod interfejs. Największa baza
   legacy w PL; koszt developmentu już poniesiony.
3. **Konektor chmurowy Dotykačka** — cloud-to-cloud, **nie w agencie**, tylko moduł backendu
   (`backend/integracje/dotykacka.py`, OAuth + webhooki). Jedyny cloud-POS bez umowy partnerskiej.
4. **Faza 2:** drivery `soga_firebird` + `x2_postgres`; **KSeF** jako konektor B2B/koszty (od 04.2026);
   GoPOS po zdobyciu referencji (wymaga umowy partnerskiej).

## 4. Instalacja u klienta — kreator w panelu

Ustawienia → **„Integracja POS"** (widoczna przy `modul_pos=True`):

1. Wybór źródła: Gastro · SOGA · X2 · Dotykačka · CSV/ręcznie · „inny POS" (formularz zgłoszenia
   → feed roadmapy driverów).
2. Cloud POS: formularz OAuth/API-key + test połączenia.
3. POS lokalny: panel generuje **token agenta** (losowy, hash w DB, przycisk „unieważnij") i **paczkę
   ZIP**: agent + wypełniony `config.yaml` (URL instancji, token, driver, domyślne SQL-e) + `install.ps1`
   rejestrujący usługę Windows. Właściciel przekazuje ZIP serwisantowi POS — do uzupełnienia na miejscu
   zostaje tylko connection string read-only.
4. Kreator polluje `GET /api/pos/status`; po pierwszym heartbeacie pokazuje „Agent połączony ✓".
5. Krok mapowań: pracownicy POS → pracownicy Lokalo (propozycje fuzzy, ręczne zatwierdzenie →
   tabela `PracownikPosId(pracownik_id, zrodlo, pos_id)`), rewiry → sale, formy płatności.

## 5. Zmiany kontraktu API (wyłącznie addytywne!)

Działający agent (Gastro/Rajcula) musi przeżyć każdy deploy — istniejących endpointów nie ruszamy.

| Zmiana | Szczegół |
|---|---|
| `POST /api/pos/utarg-dnia` | `{"dni":[{"data","netto","gotowka"?,"karta"?,"liczba_rachunkow"?}],"zrodlo":"..."}`; upsert po `(data, zrodlo)`; zasila pulpit/prognozę |
| `POST /api/pos/heartbeat` | `{wersja, driver, capabilities, ostatni_sync, bledy[]}` → tabela `AgentStatus`; panel pokazuje zdrowie agenta, alert gdy cisza |
| Aliasy `/api/pos/*` | te same handlery co `/api/rcp/ingest` i `/api/gastro/*`; stare ścieżki = deprecated-but-forever |
| Autoryzacja | token per lokal z DB (hash, unieważnialny) zamiast wyłącznie env `RCP_INGEST_TOKEN` (env zostaje jako fallback); akceptować `X-RCP-Token` oraz `Authorization: Bearer` |
| Formy płatności | enum `gotowka\|karta\|przelew\|inne` + normalizacja legacy w handlerze |
| Allowlista | nowe ścieżki `/api/pos/*` dopisać do tablicy tras publicznych role_guard |

## 6. Ryzyka

1. **Wsteczna zgodność agenta Rajculi** — stąd wyłącznie aliasy; test kontraktowy starych payloadów w CI.
2. **Mapowanie pracowników po imieniu jest kruche** — tabela `PracownikPosId` + krok kreatora to warunek
   skalowania; bez tego każdy nowy lokal = tickety supportowe.
3. **Agent „umiera po cichu" u klienta** — heartbeat wchodzi w MVP; auto-update i podpisywanie paczek
   przed ~10. instalacją.
4. **Dystrybucja runtime'u** — docelowo pojedynczy `.exe` (PyInstaller) per driver; dla Gastro zostaje
   też wariant czysto-PowerShellowy (zero instalacji).
5. **GoPOS/POSbistro wymagają umów partnerskich** — nie planować przed referencjami.
