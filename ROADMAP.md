# Roadmapa produktu: Grafik Pracy → SaaS dla gastronomii

*Wersja 1.0 · dla właściciela (Oskar) · czerwiec 2026*

> Dokument powstał z wieloagentowej analizy zakotwiczonej w realnym kodzie (6 soczewek pomysłów
> + głęboki projekt systemu rezerwacji). Każdy moduł stoi za flagą w `LokalConfig` (sprzedawalny
> per lokal) i reużywa istniejące encje zamiast budować obok.

## 1. Gdzie jesteśmy, dokąd idziemy

Mamy działającą, bogatą w dane aplikację (FastAPI + React/PWA + lokalny agent RCP/Gastro), która domyka realny obieg gastronomii: grafiki z auto‑układaniem, RCP→wypłaty, rozliczenia kasowe dnia, imprezy/wesela i zadatki KP. Fundamenty komercjalizacji są już położone (fail‑fast sekretów, CORS secure‑by‑default, Alembic + baseline, rola/flagi na Stanowisku, encja `LokalConfig`, white‑label, 268 testów). **Brakuje jednego flagowego modułu, który zamieni produkt z „lepszego Excela" w sprzedawalny SaaS: dwukierunkowych rezerwacji.** Dziś rezerwacje to wyłącznie jednokierunkowy import liczb z Google Calendar (`backend/rezerwacje.py`, pracownik widzi tylko liczby). Kierunek: zbudować realny moduł rezerwacji stolików/sal/terminów **na istniejącej encji `Termin`** (nie obok niej), a wokół niego — warstwami — domknąć no‑show, zadatki online, plan sali i events. Wszystko za flagą w `LokalConfig`, sprzedawalne per lokal w abonamencie.

---

## 2. Flagowy moduł: ROZBUDOWANY SYSTEM REZERWACJI

### Wizja
Pełny cykl życia rezerwacji tworzonej **w aplikacji** (i opcjonalnie online przez gościa), zamiast biernego podglądu cudzego kalendarza: `rezerwacja → potwierdzona → odbyła / no_show / odwołana`, ze slotami, godzinami otwarcia, pojemnością stolików/sal, zadatkami i potwierdzeniami — spięty z grafikiem obsady i modułem imprez.

### Zasada przewodnia: budować NA istniejącym kodzie
- **Rozszerzamy `Termin` (`backend/models.py`), nie tworzymy trzeciej równoległej encji.** `Termin` już ma datę, klienta, telefon, salę, liczbę osób, status (`rezerwacja|odbyla|odwolana`), zadatek, `ical_uid` i powiązanie z `KpZadatek`. To naturalny rdzeń.
- **Dwa rozmiary rezerwacji, jedna encja:** lekka rezerwacja stolika („4 os., 18:00") vs ciężka impreza/sala (wesele). Rozróżnia je nowe pole `rodzaj`. Tylko `rodzaj=sala/impreza` generuje `Impreza`→obsadę (mechanizm `ical:{uid}` już działa); `rodzaj=stolik` **nigdy** nie tworzy `Impreza` (twarda, przetestowana reguła — inaczej zasypie grafik fałszywymi wymaganiami).
- **Import Google/.ics zostaje jednym z kanałów** (`kanal=google|ical`), nie osobnym światem. Ekran „liczby na żywo" (`Rezerwacje.jsx`) zostaje jako widok ruchu dla pracownika (**tylko liczby — zero danych klienta, wymóg RODO**); nowy CRUD to widok admina/szefa.
- **Cały moduł za nową flagą `LokalConfig.modul_rezerwacje`** (jeszcze nie istnieje — obok są `modul_rozliczenia/imprezy/pos/sprzatanie`). Wzorzec guardu jak `modul_imprezy`.

### Zakres MVP (konkret wdrożeniowy)
| Element | Co dokładnie |
|---|---|
| Migracja Alembic **0003** | Rozszerzenie `Termin` + backfill: `ical_uid≠NULL → rodzaj=impreza`, inaczej `rodzaj=stolik`; statusy 1:1. Błąd backfillu rozjeżdża kalendarz imprez — testować pierwsze. |
| Nowe pola `Termin` | `godz_od`, `godz_do` (Time), `kanal` (`reczna\|online\|google\|ical`), `rodzaj` (`stolik\|sala\|impreza`), `stolik_id` (FK→stoliki, SET NULL), `email`, `token_potwierdzenia`, `potwierdzono_at`, `odwolano_at` |
| Rozszerzony enum statusu | `rezerwacja\|potwierdzona\|odbyla\|no_show\|odwolana` (wstecznie zgodny) |
| Encja **Stolik** (nowa) | `nazwa/numer`, `strefa`, `pojemnosc`, `laczy_sie`, `aktywny`, `kolejnosc`. Sala jako string na start; pełna encja `Sala` później. |
| Encja **GodzinyOtwarcia** (nowa) | `dzien_tygodnia` (0–6), `godz_od`, `godz_do`, `ostatni_zasiadek`, `dlugosc_slotu_min` (def. 120), `aktywny` |
| Flaga `LokalConfig.modul_rezerwacje` | Boolean + guard w endpointach + warunkowa zakładka we froncie |
| Endpointy | Reuse GET/POST/PUT/DELETE `/api/terminy` + filtry `rodzaj/status/stolik`; nowy `POST /api/terminy/{id}/status` (przejścia + timestampy); **walidacja overlap** stolika w oknie `[godz_od, godz_do]` i pojemności sali (w transakcji — ryzyko double‑bookingu) |
| Frontend | Nowy widok „Rezerwacje (zarządzanie)" dla admina/szefa, styl reuse `KalendarzImprez.jsx/Imprezy.jsx`. Stary `Rezerwacje.jsx` karmiony też rekordami `Termin rodzaj=stolik`. |
| Powiadomienia | Web Push do admina/szefa o nowej rezerwacji (reuse `push.py`) |
| Testy | Rozszerzyć `test_rezerwacje.py`/`test_kalendarz.py`: pojemność, kolizje slotów, przejścia statusów, backfill 0003 |

### Przepływy w pigułce
1. **Admin → rezerwacja w aplikacji (MVP):** formularz (data, godz, stolik, osoby, klient, telefon) → `POST /api/terminy` `rodzaj=stolik, kanal=reczna` → walidacja pojemności + overlap → status `potwierdzona`.
2. **Dzień rezerwacji:** gość przyszedł → `odbyla`; nie przyszedł → `no_show` (timestamp, opcj. przepadek zadatku).
3. **Odwołanie:** gość (link/token) lub admin → `odwolana` → zwolnienie slotu + push.
4. **Sprzężenie z grafikiem:** `rodzaj=sala/impreza` → `Impreza` → `algorithm.przelicz_imprezy_na_wymagania` → obsada (istnieje); `rodzaj=stolik` → **tylko** sygnał ruchu.
5. **Online (za flagą `rezerwacje_online`, później):** widget bez logowania → silnik liczy wolne sloty → opcjonalny zadatek → `Termin kanal=online` + token + push.

### Ryzyka (z projektu modułu)
- **RODO:** rezerwacje online wprowadzają dane osobowe gości — zgoda, retencja; ekran pracownika nadal TYLKO liczby.
- **Double‑booking:** walidacja overlap w transakcji + constraint, inaczej overbooking.
- **Migracja statusów/backfill 0003:** zachować istniejące wartości; błąd rozjeżdża kalendarz imprez.
- **Strefy czasowe:** wprowadzenie godzin wymaga jednolitej obsługi TZ (dziś `.ics` świadomie ignoruje godziny).
- **Przeskalowanie:** trzymać MVP przy rezerwacji stolika + statusy + pojemność; online/płatności/SMS jako wyraźne „później".

---

## 3. Backlog pomysłów (epiki posortowane wg wartości)

### EPIK A — REZERWACJE i OBSŁUGA GOŚCI *(priorytet właściciela)*
| Pomysł | Wartość | Nakład |
|---|---|---|
| Rdzeń: Stolik/Sala/Slot + dwukierunkowy `Termin` | wysoka | L |
| Godziny otwarcia + sloty + dostępność live | wysoka | L |
| Widget rezerwacji online (publiczny POST) | wysoka | XL |
| Potwierdzenia/przypomnienia SMS/e‑mail (link potwierdź/odwołaj) | wysoka | L |
| Zadatki online (P24/Stripe) → zeszyt kasowy + KP | wysoka | XL |
| Obsługa no‑show: oznaczanie, auto‑zwolnienie, polityki | średnia | M |
| Lista oczekujących (waitlist) z auto‑propozycją | średnia | M |
| Interaktywny plan sali (drag&drop) + live `StanStolow` | wysoka | XL |
| Rezerwacje grupowe/eventy spięte z kalendarzem imprez | średnia | L |
| Karty gości / CRM rezerwacyjny (historia, VIP, no‑show) | średnia | M |

### EPIK B — INTEGRACJE i EKOSYSTEM
| Pomysł | Wartość | Nakład |
|---|---|---|
| Per‑tenant secret store (fundament bezpieczeństwa) | wysoka | M |
| Płatności online zadatków (P24/Stripe/BLIK) | wysoka | L |
| Generyczna warstwa konektorów POS (adapter) | wysoka | L |
| Dwukierunkowa sync kalendarzy (Google/Outlook/CalDAV) | wysoka | XL |
| Bramki SMS + transakcyjny e‑mail | wysoka | M |
| Publiczne API + webhooki (in/out) | wysoka | L |
| Konektory portali rezerwacji (MojStolik/Resmio…) | wysoka | L |
| Eksport do księgowości (KSeF/JPK/wFirma/Fakturownia) | średnia | L |

### EPIK C — FINANSE, RAPORTY, ANALITYKA
| Pomysł | Wartość | Nakład |
|---|---|---|
| Pulpit właściciela (KPI cockpit) | wysoka | L |
| Alerty anomalii kasowych | wysoka | M |
| Eksport do księgowości | wysoka | L |
| Foodcost i marża | wysoka | XL |
| Moduł napiwków (ewidencja, podział, rozliczenie) | średnia | L |
| Raporty porównawcze okresów (PoP) | średnia | M |
| Prognoza przychodów (trend + sezonowość) | średnia | L |

### EPIK D — GRAFIK i KADRY
| Pomysł | Wartość | Nakład |
|---|---|---|
| Szablony grafików (tygodnie wzorcowe) | wysoka | M |
| Prognoza obsady wg ruchu i rezerwacji | wysoka | L |
| Wymiana/oddawanie zmian (giełda zmian) | wysoka | L |
| Koszt pracy na żywo vs budżet | wysoka | L |
| Strażnik zgodności z prawem pracy (PIP) | wysoka | M |
| Ścieżki akceptacji (wnioski→szef→admin) | średnia | M |
| Powiadomienia o delcie grafiku po publikacji | średnia | M |
| Auto‑układanie z fair‑rozkładem weekendów/świąt | średnia | M |

### EPIK E — PLATFORMA SaaS i MULTI‑LOKAL
| Pomysł | Wartość | Nakład |
|---|---|---|
| Panel super‑admina nad wszystkimi lokalami | wysoka | L |
| Granularne role/uprawnienia (RBAC) | wysoka | L |
| Samoobsługowy onboarding (kreator lokalu) | wysoka | L |
| Billing i subskrypcje (abonament per lokal) | wysoka | L |
| Dziennik audytu wrażliwych operacji | wysoka | M |
| Encja Sieć/Organizacja (multi‑lokal) | wysoka | XL |
| Centralny serwis powiadomień (push+mail+SMS) | średnia | M |
| Aplikacja mobilna pracownika (PWA‑first) | średnia | L |

### EPIK F — AI i AUTOMATYZACJA
| Pomysł | Wartość | Nakład |
|---|---|---|
| Prognoza ruchu per dzień/pasmo (bez LLM) | wysoka | M |
| Auto‑grafik wspierany prognozą | wysoka | L |
| Auto‑przypomnienia/potwierdzenia rezerwacji | wysoka | M |
| Scoring no‑show + dynamiczny zadatek | wysoka | L |
| Podsumowanie dnia dla managera | średnia | M |
| Chat‑asystent nad danymi lokalu (Claude API + tool‑use) | średnia | XL |
| Asystent tekstów/komunikacji (Claude API) | niska | M |

---

## 4. Roadmapa fazowa

### TERAZ (najbliższa fala) — *rdzeń rezerwacji + fundament bezpieczeństwa*
- **Rezerwacje MVP** (Epik A, rdzeń): migracja 0003, encje `Stolik`/`GodzinyOtwarcia`, flaga `modul_rezerwacje`, CRUD admina, walidacja pojemności/overlap, widok zarządzania, push o nowej rezerwacji. **Pierwszy duży moduł po fundamentach.**
- **Per‑tenant secret store** (Epik B): tani, zrobić *zanim* narosną integracje.
- **Pulpit właściciela** (Epik C): agregacja istniejących danych, zero nowych tabel — szybki argument sprzedażowy.

### NASTĘPNE — *redukcja no‑show + monetyzacja*
- Potwierdzenia/przypomnienia SMS+e‑mail · Płatności online zadatków P24/Stripe · Obsługa no‑show + waitlista · Alerty anomalii kasowych + eksport do księgowości · RBAC + panel super‑admina.

### PÓŹNIEJ — *platforma i przewaga konkurencyjna*
- Widget rezerwacji online + dwukierunkowa sync kalendarzy · Interaktywny plan sali z live `StanStolow` · Billing/subskrypcje + samoobsługowy onboarding · Prognoza ruchu → auto‑grafik, szablony grafików, koszt vs budżet, strażnik prawa pracy · Foodcost/marża, napiwki, raporty PoP.

### WIZJA — *otwarty ekosystem + AI*
- Encja Sieć/Organizacja (multi‑lokal/franczyzy) · Publiczne API + webhooki, konektory portali i wielu POS · Chat‑asystent nad danymi, scoring no‑show z modelem uczonym, KSeF e‑faktury zadatkowe.

---

## 5. Rekomendowane „następne 3 rzeczy do zbudowania"

1. **Rezerwacje MVP — rdzeń** (migracja 0003 + `Stolik`/`GodzinyOtwarcia` + flaga `modul_rezerwacje` + CRUD admina z walidacją overlap/pojemności).
   *Dlaczego:* bezpośredni priorytet właściciela i fundament najcenniejszej soczewki. Buduje na `Termin` i mechanizmie `Impreza→obsada`. Pierwsze testy: backfill 0003 i reguła `rodzaj=stolik` ⇒ NIE tworzy `Impreza`. Twardo: overlap w transakcji + `Rezerwacje.jsx` nadal tylko liczby (RODO).

2. **Pulpit właściciela (KPI cockpit)** — `GET /api/pulpit?start&end`.
   *Dlaczego:* najwyższy stosunek wartości do nakładu — czysta agregacja danych z `raporty`, `zeszyt`, `rozliczenia`, `StolikiHistoria`. Zero nowych tabel, natychmiastowy argument sprzedażowy.

3. **Per‑tenant secret store + flaga modułowa jako wzorzec.**
   *Dlaczego:* warunek brzegowy KAŻDEJ przyszłej integracji (płatności, SMS, OAuth). Tani teraz, drogi później. Spójnie z fail‑fast `settings.py` (brak/zły sekret = integracja wyłączona z jasnym komunikatem, nie crash).

---

*Zasada nadrzędna: każdy nowy moduł stoi za flagą w `LokalConfig` (sprzedawalny per lokal) i reużywa istniejące encje/mechanizmy zamiast budować obok. Pieniądz online (zadatki) i dwukierunkowe rezerwacje to dwa ruchy, które odróżniają produkt od arkusza Excela — i one decydują o cenie abonamentu.*
