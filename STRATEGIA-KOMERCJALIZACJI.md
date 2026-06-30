# Strategia komercjalizacji „Grafik Pracy"
### Od aplikacji jednego lokalu (Karczma Rajcula) do produktu SaaS sprzedawalnego gastronomii

*Dokument decyzyjny dla właściciela (Oskar Olejnik). Stan na 2026-06-28.*

> **Decyzje kierunkowe podjęte przez właściciela:**
> 1. **Model:** SaaS hostowany przez Ciebie (klient nic nie instaluje, abonament).
> 2. **Rynek:** szeroko — każda gastronomia, produkt uniwersalny z konfiguracją per typ lokalu.
> 3. **Priorytet:** solidne fundamenty (multi-tenant + bezpieczeństwo + RODO) **przed** sprzedażą.

---

## 1. Streszczenie zarządcze

Aplikacja jest **dojrzała funkcjonalnie**, ale technicznie to system zbudowany dla **jednego lokalu** — z brandingiem Rajculi, logiką biznesową zaszytą na sztywno i bez warstwy konfiguracji, izolacji danych czy automatycznego wdrażania.

Zgodnie z Twoim wyborem celem jest **SaaS hostowany przez Ciebie**. Rekomendowana architektura tego SaaS to **instance-per-tenant** (każdy klient = własny izolowany kontener + baza, wszystkim zarządzasz centralnie) — nie współdzielona baza multi-tenant. Z perspektywy klienta to nadal czysty SaaS (przeglądarka, abonament, zero instalacji), ale dane płacowe każdej firmy są **fizycznie odseparowane** — najsolidniejszy fundament dla RODO i Twojego priorytetu „fundamenty najpierw". Współdzieloną bazę multi-tenant (klasy XL, z wbudowanym ryzykiem wycieku płac) wprowadza się dopiero przy ~30–50+ klientach.

Sprzedaż: **subskrypcja per-lokal (flat)** w trzech pakietach (Start 99 / Pro 199 / Premium 349 PLN/mies.), z integracją POS jako płatnym dodatkiem. Licencja egzekwowana **podpisanym plikiem Ed25519** z degradacją do trybu „tylko do odczytu" zamiast kasowania danych.

**Czas do produktu sprzedawalnego drugiej firmie: ~2–3 miesiące pracy jednoosobowo** (Fazy 0–1). Pełna automatyzacja skali — kolejne 2–3 miesiące.

**Największe ryzyko techniczne:** logika rozpoznająca stanowiska **po nazwie** (np. „Kuchnia", „Sala") decyduje o **WYPŁATACH** — jeśli drugi klient nazwie stanowisko inaczej, system **cicho policzy złe pieniądze**.
**Największe ryzyko biznesowe:** RODO — sprzedaż systemu przechowującego dane płacowe wielu firm bez szyfrowania, audytu dostępu i pakietu prawnego (DPA) to ekspozycja na karę i utratę zaufania.

---

## 2. Ocena stanu obecnego

| Obszar | Gotowość | Komentarz |
|---|:---:|---|
| Wielodzierżawność / izolacja danych | **1/10** | Zero pojęcia tenanta; ~175 zapytań widzi całą bazę. Ale architektura „jeden kontener = jeden lokal" pasuje do rekomendowanego instance-per-tenant. |
| Konfigurowalność (logika Rajculi) | **2/10** | Stanowiska rozpoznawane po nazwie stringa, tydzień środa→wtorek, mapy sal, współczynniki obsady — wszystko na sztywno; brak encji konfiguracji lokalu. |
| White-label / branding / i18n | **1/10** | „Rajcula" wmurowana w ~9 plików, logo binarne, kolory kompilowane, zero infrastruktury tłumaczeń (~342 polskie stringi w 57 plikach). |
| Infrastruktura / wdrożenie (Ops) | **2/10** | Brak Dockerfile (tylko Postgres), brak Alembic, brak CI/CD, backupów, monitoringu, provisioningu. Wdrożenie = dni eksperckiej pracy. |
| Bezpieczeństwo i RODO | **2/10** | `SECRET_KEY='dev-secret-change-me'`, CORS `*`, brak rate-limitu, brak szyfrowania at-rest, brak audit logu, brak pakietu prawnego. |
| Integracja POS (Gastro LSI) | **3/10** | Twardo przywiązana do jednego POS, ale kontrakt agent↔API jest rozsądnie odseparowany (JSON/HTTPS) — da się go sformalizować. |

**Ogólna gotowość komercyjna: ~2/10.** Bogata funkcjonalność, fundament produktowy do zbudowania.

---

## 3. Rekomendowana strategia

### Model wdrożenia: **SaaS zarządzany w architekturze instance-per-tenant**
Każdy klient = własny kontener Docker z własną bazą, hostowany i zarządzany przez Ciebie z centralnego panelu. Izolacja danych **fizyczna** — zero ryzyka wycieku bez przepisywania ~175 zapytań. To rząd wielkości **M–L**, nie XL. Ten sam artefakt da się później sprzedać on-premise klientom, którzy zażądają danych u siebie.

> **Dlaczego nie współdzielona baza multi-tenant (od razu):** to projekt klasy **XL** z wbudowanym ryzykiem wycieku danych płacowych (jeden błąd w filtrze `tenant_id` = wyciek płac wszystkich firm). Opłacalny ekonomicznie dopiero przy setkach klientów. Wchodzimy w niego dopiero w Fazie 3+ — gdy liczba instancji zacznie podbijać koszty hostingu.

### Model licencji: **podpisany plik Ed25519 + heartbeat z okresem łaski**
Klucz publiczny w instancji, prywatny tylko u Ciebie — klient nie podrobi licencji. Kill-switch działa przez **stopniową degradację**:
`OK → GRACE (baner przypominający) → READ_ONLY (blokada zapisów, ale podgląd i eksport działają) → LOCKED`.
**Nigdy nie kasujemy danych ani nie blokujemy eksportu** — to wymóg RODO i zaufania. MVP licencji (sam podpisany plik + tryb READ_ONLY, bez serwera licencji) = ~1 tydzień.

### Cennik: subskrypcja per-LOKAL (flat), nie per-pracownik

| Pakiet | Cena (netto/mies., przy umowie rocznej) | Zakres |
|---|:---:|---|
| **Start** | **99 PLN** | Grafik + dyspozycje + publikacja + role + push. Bez POS, bez rozliczeń, bez imprez. |
| **Pro** *(flagowy)* | **199 PLN** | Start + ręczny/PIN RCP + liczenie godzin do wypłat + rozliczenia kasowe + raporty. |
| **Premium / Eventowy** | **349 PLN** | Pro + moduł imprez/wesel (zadatki KP, obsada per goście, sprzątanie sal) + white-label. |
| **Add-on POS** | **+149 PLN/mies. + 990–1990 PLN wdrożenie** | Automatyczny RCP z Gastro LSI. Upsell do Pro/Premium. |

**Dlaczego flat per-lokal, nie per-pracownik** (konkurencja typu Kadromierz liczy ~13 PLN/os.): koszt po Twojej stronie jest per-instancja, restauracje mają dużą rotację, a model flat zdejmuje z klienta „karę za zatrudnianie". Niszą, w której jesteś najmocniejszy, są **domy weselne / lokale eventowe** — tam ogólne systemy do grafików nie wystarczają, a POS tego nie robi.
Cykl: miesięczny + roczny z rabatem ~17%. Onboarding: 299–499 PLN (bez POS), promocyjnie „0 zł przy umowie rocznej".
**Subskrypcja, nie licencja wieczysta** — produkt wymaga ciągłego utrzymania i hostingu; recurring revenue to jedyny sensowny model.

---

## 4. Co MUSI być zrobione przed pierwszą sprzedażą (blokery)

*Pracochłonność: **S** = dni, **M** = ~1–2 tyg., **L** = ~2–4 tyg., **XL** = miesiące.*

### Bezpieczeństwo / RODO
- **[S]** **Fail-fast na sekretach:** aplikacja odmawia startu, gdy `SECRET_KEY` / `RCP_INGEST_TOKEN` / `DATABASE_URL` mają wartości domyślne. *Najtańszy blocker, eliminuje przejęcie konta admina.*
- **[M]** CORS domyślnie zamknięty (lista origin per wdrożenie), rate-limit + lockout na logowaniu.
- **[L]** Audit log dostępu do danych płacowych, polityka retencji, endpoint eksportu/usunięcia danych (prawa podmiotu RODO).
- **[M]** Generowanie unikalnego `SECRET_KEY` i tokenu RCP przy każdym provisioningu.

### Wdrożenie / Ops
- **[L]** Dockerfile backend + frontend + reverse proxy z auto-HTTPS (Caddy/Traefik). Dziś `docker-compose` stawia tylko Postgres.
- **[L]** **Alembic** zamiast hacka `_ensure_schema()` — warunek konieczny bezpiecznej aktualizacji wielu baz. *Bez tego nie zaktualizujesz nawet 3 klientów.*
- **[L]** Skrypt provisioningu `new_client`: generuje sekrety, bazę, admina z bezpiecznym hasłem, subdomenę. „Dni" → „minuty".
- **[M]** Backup (`pg_dump` z retencją) + healthcheck (DB + świeżość RCP) jako standard instancji.

### Konfigurowalność (likwidacja logiki Rajculi)
- **[L]** Encja `LokalConfig`/Settings — fundament parametryzacji (start tygodnia, branding, współczynniki obsady, daty, flagi modułów).
- **[L]** **Refaktor logiki „po nazwie stringa" na flagi na encji `Stanowisko`** (typ + flagi `pelne_godziny_rcp`, `priorytet_obsady`, `zamyka_lokal`, `daje_dostep_zamowien`). *Najgroźniejsza klasa błędów — decyduje o wypłatach.*
- **[M]** Wyłączalność modułów branżowych (rozliczenia kasowe, imprezy, POS, sprzątanie) za flagą.
- **[M]** Parametryzowany seed / kreator onboardingu zamiast `seed.py` z danymi Rajculi.

### White-label
- **[L]** `brand_name` z configu (scalenie `Raj<span>cula</span>`), logo jako URL, kolory jako zmienne CSS runtime, sparametryzowany manifest PWA + Electron `appId`.
- **[M]** Usunięcie zaszytej ścieżki `/Users/rajcula/...` z `electron/main.js`; target Windows w electron-builder.

### Prawne *(⚠️ nie jest to porada prawna — wymaga prawnika IT + specjalisty RODO)*
- **Rozstrzygnięte Twoją decyzją (SaaS hostowany przez Ciebie):** jesteś **procesorem** danych (RODO art. 28) → **wymagana umowa powierzenia przetwarzania (DPA)** z każdym klientem.
- **[L]** Pakiet wzorów: EULA/regulamin SaaS, polityka prywatności, **DPA**, polityka retencji, procedura naruszeń (72h), rejestr czynności przetwarzania.
- **[S]** Konsultacja księgowego: JDG vs sp. z o.o. (odpowiedzialność majątkowa za wyciek danych N firm), status VAT, ryczałt 12%.

---

## 5. Definicja „MVP dla drugiego klienta"

Drugi klient (zwykła restauracja, bez Gastro, bez wesel) musi móc używać **rdzenia: grafik + dyspozycje + publikacja + role + push**. Reszta to dodatki wyłączalne. Minimum:

1. **Encja `LokalConfig`** — jeden rekord per instancja (branding, start tygodnia, współczynniki, flagi modułów).
2. **Flagi na `Stanowisko`** zamiast rozpoznawania po nazwie — *inaczej drugi klient nazwie stanowisko „Kelner" i dostanie złe godziny.*
3. **Wyłączalność modułów** (POS, rozliczenia, imprezy za flagą) — restauracja włącza tylko rdzeń.
4. **Kreator/parametryzowany seed** + pierwszy admin z bezpiecznym hasłem (nie `admin/admin123`).
5. **Fail-fast sekretów** + zamknięty CORS.
6. **Dockerfile + Alembic** — powtarzalne wdrożenie i bezpieczna aktualizacja.
7. **White-label etap 1** (nazwa/logo/kolory z configu, bez tłumaczenia UI — drugi klient też jest polski).

**Czego NIE robić w MVP:** współdzielona baza multi-tenant, i18n UI (react-i18next, ~342 stringi), generalizacja konektorów POS. Drugi klient z POS → trzymaj `modul_pos` wyłączony i wejdź z ręcznym/PIN RCP.

---

## 6. Mapa drogowa fazowa

### Faza 0 — Fundamenty bezpieczeństwa i powtarzalności *(~2–3 tyg.)*
**Cel:** instancja, którą da się bezpiecznie postawić i zaktualizować.
**Zadania:** fail-fast sekretów, zamknięty CORS; **Alembic** (z migracją bazującą na obecnym schemacie + backfill dla Rajculi); Dockerfile backend+frontend; reverse proxy z auto-HTTPS.
*Rajcula przechodzi na ten sam stack — staje się „klientem zero" i testem procesu wdrożenia.*

### Faza 1 — MVP komercyjne *(~3–4 tyg.)*
**Cel:** drugi klient = jedno polecenie; produkt działa pod dowolnym (polskim) lokalem.
**Zadania:** `LokalConfig` + flagi na `Stanowisko` + refaktor logiki po nazwach + wyłączalność modułów; skrypt provisioningu (sekrety, baza, admin); parametryzowany seed/kreator; backup + healthcheck per instancja; white-label etap 1; MVP licencji (podpisany plik + READ_ONLY).

### Faza 2 — Skalowanie i automatyzacja wdrożeń *(~4–6 tyg.)*
**Cel:** wdrożenie w minuty, bez programisty; sprzedaż pod marką klienta.
**Zadania:** CI/CD (pytest + build obrazów + tag wersji); serwer licencji (`/activate`, heartbeat, limity, feature flags, panel wydawania); ręczny/PIN RCP jako domyślne źródło godzin (warunek, by Start/Pro działały bez POS); billing (Stripe / Przelewy24 + strona pakietów); target Windows w Electron, naprawa ścieżki Pythona.

### Faza 3 — Dojrzałość *(później, ~2–3 mies.)*
**Cel:** zarządzanie flotą instancji, oferta eventowa, pełna gotowość prawna.
**Zadania:** panel super-admina nad N instancjami; szablony per typ lokalu (restauracja / dom weselny / kawiarnia); instalator agenta POS dla Windows + katalog konektorów (generic SQL, CSV); parametryzacja modułu imprez/sal; i18n UI; monitoring/alerty produkcyjne.
*Współdzielona baza multi-tenant — rozważać dopiero przy 30–50+ klientach, gdy koszt floty instancji zacznie boleć.*

**Łącznie do produktu sprzedawalnego (Fazy 0–1): ~2–3 mies. jednoosobowo.**

---

## 7. Ryzyka i otwarte decyzje

**Ryzyka krytyczne:**
- **Ciche błędy w wypłatach** — logika po nazwie stanowiska decyduje o pieniądzach; refaktor na flagi musi objąć WSZYSTKIE miejsca (`SALA_PREFIX`, `== 'Kuchnia'`, `== 'Techniczny'`, `'imprez' in nazwa` itd.).
- **Migracja Rajculi bez Alembic jest nieodwracalna** — Alembic MUSI wejść przed jakąkolwiek zmianą modelu.
- **RODO bez pokrycia** — DPA bez realnych środków technicznych (szyfrowanie, audit log) to deklaracja bez pokrycia; przy danych płacowych ryzyko kary i utraty zaufania.
- **Koszt operacyjny rośnie liniowo** — bez automatyzacji provisioningu N klientów = N ręcznych instancji; zabija marżę przy 5+ klientach. *(Dlatego skrypt `new_client` jest w blokerach, nie w „miło mieć".)*

**Decyzje, które potrzebuję od Ciebie, by ruszyć z implementacją:**
1. **Kto jest realnym drugim klientem?** Restauracja bez POS (łatwy MVP) czy dom weselny (wymaga modułu imprez — większy zakres Fazy 1)? *Determinuje priorytety.*
2. **Forma działalności:** zostajesz na JDG czy zakładasz sp. z o.o.? *(Odpowiedzialność majątkowa za wyciek danych N firm — przy SaaS jesteś procesorem.)*
3. **Budżet na pakiet prawny** (~5–15 tys. zł za wzory DPA/EULA/polityk) — to koszt wejścia w model SaaS, nie opcja.
4. **Akceptacja cennika** (99/199/349 PLN flat) — czy świadomie konkurujemy ceną flat zamiast per-pracownik?

---

## 8. Pierwsze 3 kroki na ten tydzień

1. **Wdróż fail-fast na sekretach** (`backend/auth.py:15`, CORS w `backend/main.py:31`) — aplikacja odmawia startu przy `dev-secret-change-me` i domyślnym CORS `*`. Kilka godzin pracy, a zamyka najgroźniejszą trywialną lukę (podrobienie tokenu admina). **Najtańszy, największy efekt.**
2. **Umów dwie konsultacje równolegle do kodu:** (a) prawnik prawa IT + specjalista RODO — komplet wzorów (EULA, DPA, polityki) pod model SaaS; (b) księgowy — JDG vs sp. z o.o., status VAT. Te procesy trwają tygodniami — uruchom je teraz.
3. **Wprowadź Alembic i zrób pierwszą migrację bazującą na obecnym schemacie Rajculi** (z backfillem) — warunek konieczny wszystkich dalszych zmian modelu (`LokalConfig`, flagi `Stanowisko`). Bez tego każda zmiana schematu zagraża danym produkcyjnym pierwszego klienta.

---

*⚠️ **Zastrzeżenie:** części prawna i podatkowa tego dokumentu (sekcje 3, 4, 7, 8) mają charakter informacyjny z perspektywy produktowej i **NIE stanowią porady prawnej ani podatkowej**. Przed pierwszą sprzedażą skonsultuj komplet z prawnikiem prawa IT/handlowego, specjalistą RODO/IOD oraz doradcą podatkowym. Koszt konsultacji jest nieporównywalnie niższy niż kara UODO (do 20 mln EUR / 4% obrotu) lub proces z klientem.*

---
*Dokument wygenerowany na podstawie wieloagentowego audytu kodu (6 obszarów) + projektu strategii (5 obszarów). Analiza techniczna oparta na realnym kodzie projektu.*
