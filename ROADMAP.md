# Roadmapa produktu Lokalo → SaaS dla gastronomii (v2 · lipiec 2026)

> Metodologia: 64 pomysły wygenerowane przez 8 niezależnych „soczewek" (monetyzacja, AI,
> goście, kuchnia, HR, integracje PL, skala/sieci, luki konkurencji — z researchem rynku),
> ocenione przez panel 3 sędziów o różnych perspektywach (founder SaaS · pragmatyczny CTO
> solo-dev · właściciel 2 restauracji i domu weselnego). Skale 1–5: **impact** (czy sprzedaje
> abonamenty / realna wartość operacyjna), **feasibility** (czy solo-dev dowiezie),
> **moat** (czy wyróżnia na rynku). Poprzednia wersja roadmapy: historia gita.

---

## 1. Gdzie jesteśmy (stan na 07.2026)

Z poprzedniej roadmapy **zbudowane i działające**: rezerwacje stolików online (widget publiczny,
plan sali drag&drop, CRM gości + scoring no-show), prognoza ruchu → prognoza obsady →
auto-wymagania grafiku + alerty niedoboru, pulpit KPI + alerty anomalii kasowych, napiwki,
giełda zmian, eksport wypłat XLSX, billing/licencje, samoobsługowy onboarding, RODO
(szyfrowanie at-rest, audyt płac, rate-limit), Docker+Caddy, provisioning `new_client`,
CI/CD, instalator desktop, branding **Lokalo** + design system **„Cicha scena"**.

Fundament jest. Ta roadmapa odpowiada na pytanie: **co zbudować, żeby Lokalo sprzedawało się
samo** — i wygrywało z Kadromierzem/inEwi (grafiki), MojStolik/resOS (rezerwacje) i modułami POS.

## 2. Trzy osie strategiczne (wnioski z rankingu)

### Oś A — „Wesela i imprezy": wertykał, którego nikt nie obsługuje ⭐
Najmocniejszy sygnał panelu. Systemy rezerwacyjne kończą na stolikach; systemy bankietowe
obsługują managera, nie klienta. **Domy weselne i lokale eventowe w Polsce nie mają żadnego
dedykowanego narzędzia** — a Lokalo już ma kalendarz imprez, zadatki, obsadę per goście
i rozliczenia imprez. To nasz klin w rynek (beachhead): klient weselny płaci najwięcej,
ból jest największy, konkurencja zerowa.

### Oś B — „Zgodność i ochrona pieniędzy": funkcje, za które płaci się ze strachu
Sanepid, PIP, koncesja alkoholowa, nadużycia kelnerskie, skokowe podwyżki cen dostawców.
Kary idą w tysiące złotych, nadużycia to typowo 1–3% obrotu. Funkcje z tej osi mają
najwyższą feasibility (budujemy na istniejącym: strażnik prawa pracy, Web Push, agent POS,
zeszyt kasowy) i **argument sprzedażowy, który zamyka rozmowę**: „to się zwraca po pierwszej
uniknionej karze / pierwszym wykrytym kombinatorze".

### Oś C — „Załoga, która zostaje": retencja pracowników jako produkt
Rotacja to plaga gastro. Lokalo już liczy zarobki co do minuty — pokazanie ich pracownikowi
na żywo (+ zaliczki, + radar odejść dla managera) buduje lojalność załogi wobec lokalu
**i lojalność lokalu wobec Lokalo** (dane, których nie zabierze się do konkurencji).

## 3. Roadmapa fazowa

### TERAZ — najbliższa fala *(szybkie zwycięstwa + otwarcie osi weselnej)*

| # | Funkcja | Co robi | Sędziowie (i/f/m) | Wysiłek |
|---|---|---|---|---|
| 1 | **Moduł „Zgodność lokalu"** (fuzja pomysłów: terminarz zgodności + strażnik badań i sanepidu) | Cyfrowa teczka: badania sanepidowskie, medycyna pracy, BHP per pracownik + „papiery lokalu" (koncesja alkoholowa i jej raty 31.01/31.05/30.09, gaśnice, wentylacja). Alerty push 30/14/3 dni; **auto-grafik blokuje/flaguje osobę z przeterminowanymi badaniami** — tego nie ma nikt. | 4.0 / 4.7–5.0 / 3.5 | **S+M** |
| 2 | **Skrzynka zapytań o imprezy z AI** ⭐ TOP 1 rankingu | Właściciel wkleja mail „szukamy sali na wesele, ~120 osób, sierpień 2027, 250 zł/os" → Claude (tool-use) wyciąga parametry, sprawdza kalendarz imprez, proponuje wolne terminy i **generuje szkic odpowiedzi + kartę imprezy do zatwierdzenia 1 kliknięciem**. Pary rezerwują u tego, kto odpisze pierwszy — każda godzina zwłoki to utracone 20–50 tys. zł. | 4.3 / 4.0 / 4.0 | **M** |
| 3 | **Radar odejść pracowników** | Sygnały z danych, które już są: spadek dyspozycyjności, oddawanie zmian na giełdzie, malejące godziny → cichy alert dla managera „porozmawiaj z Anią, zanim złoży wypowiedzenie". | 3.0 / 5.0 / 3.3 | **S** |

### NASTĘPNE — kwartał po „TERAZ" *(monetyzacja osi weselnej + ochrona pieniędzy)*

| # | Funkcja | Co robi | Sędziowie | Wysiłek |
|---|---|---|---|---|
| 4 | **Portal klienta imprezy** (etap 1, w abonamencie) | Tokenowa strona dla pary młodej/organizatora (jak istniejący widget rezerwacji): liczba gości, wybory menu, harmonogram wpłat, ustalenia z pisemnym śladem. Zmiany wpadają do karty imprezy i prognozy obsady. Koniec „to ile w końcu będzie tych gości?". | 4.7 / 4.0 / 4.3 | **M** |
| 5 | **Portal Pary Młodej** (etap 2, płatny add-on 149–199 zł/mc) | Rozbudowa etapu 1: para **sama rozsadza gości na planie sali** (drag&drop już jest!), płaci raty online (P24/BLIK), wybiera menu z wariantami. Dom weselny robiący 40 wesel/rok płaci 2–3× wyższy abonament — i nigdy nie odejdzie. | 4.7 / 3.3 / 4.3 | **L** |
| 6 | **Antyfraud POS: storna i rabaty** ⭐ TOP 3 | Agent lokalny czyta z Gastro storna/anulacje/rabaty per kelner; model statystyczny porównuje do zespołu (z poprawką na ruch), Claude pisze po polsku tygodniowe podsumowanie: „Marek stornuje 3× częściej, głównie napoje po 22:00". Komunikowane jako *flagi do rozmowy*, nie oskarżenia. | 4.3 / 3.7 / 4.0 | **M** |
| 7 | **Portfel pracownika na żywo** | Licznik „zarobiłeś już X zł w tym miesiącu" (RCP już to liczy) + symulacja „weź zmianę z giełdy = +180 zł" + wniosek o zaliczkę z limitem %, akceptacja 1 kliknięciem, auto-potrącenie z wypłaty. 80% wartości fintechów „wypłata na żądanie" — w cenie abonamentu. | 4.0 / 4.0 / 3.7 | **M** |

### PÓŹNIEJ — druga połowa horyzontu *(ekosystem polski + kuchnia)*

| # | Funkcja | Co robi | Sędziowie | Wysiłek |
|---|---|---|---|---|
| 8 | **Skrzynka kosztów z KSeF** | KSeF 2.0 (obowiązkowy!) → Lokalo samo pobiera faktury zakupowe, kategoryzuje koszty, **alarmuje o skokowych podwyżkach cen dostawców** („schab +18% vs poprzednia dostawa"), komplet miesiąca 1 kliknięciem do księgowej. Realne koszty na bieżąco, nie 20-go u księgowej. | 4.0 / 3.3 / 3.7 | **L** |
| 9 | **HACCP w telefonie** | Checklisty temperatur/czystości na telefonie pracownika z podpisem i godziną; raport „pod kontrolę sanepidu" 1 kliknięciem. Naturalne domknięcie modułu Zgodność. | 4.0 / 4.0 / 3.3 | **M** |
| 10 | **Lejek opinii Google** | Po wizycie (rezerwacja zamknięta) SMS/mail z prośbą o ocenę; niezadowoleni trafiają do formularza wewnętrznego zamiast do publicznej jedynki. Więcej gwiazdek = więcej gości. | 4.0 / 4.3 / 2.0 | **M** |
| 11 | **Konektory POS chmurowych** (Dotykačka / GoPOS / POSbistro) | Adapter na wzór istniejącego agenta Gastro — otwiera rynek lokali, które nie mają Gastro (większość nowych). Warunek skali. | 4.3 / 3.0 / 3.7 | **L** |
| 12 | **Faktury weselne → KSeF** | Wystawianie faktur za imprezy (zadatki/raty już są w systemie) prosto do KSeF — bez przepisywania do programu księgowego. | 4.0 / 3.3 / 3.3 | **M** |
| 13 | **Panel partnera dla księgowych** | Księgowa obsługująca 15 lokali widzi swoje lokale w jednym panelu (eksporty, faktury kosztowe, wypłaty) → **księgowi stają się kanałem sprzedaży Lokalo**. | 3.7 / 3.3 / 3.7 | **M** |

### ZAKŁADY (big bets) — wysoki moat, wymagają masy krytycznej klientów

| Funkcja | Dlaczego zakład | Moat |
|---|---|---|
| **Wypożyczalnia pracowników między lokalami** | Kelner z lokalu A bierze zmianę w lokalu B (oba na Lokalo) — giełda zmian ponad lokalami. Efekt sieciowy: im więcej lokali, tym większa wartość. Wymaga zaufania i masy krytycznej w jednym mieście. | 4.3 |
| **Lokalo Benchmark** | Anonimowe benchmarki: „Twój food-cost/koszt pracy/obłożenie vs podobne lokale w regionie". Dane jako produkt — nie do skopiowania przez konkurencję bez bazy klientów. | **4.7** |
| **Tryb franczyzy** | Standardy sieci (checklisty, receptury, ceny) narzucane centralnie + audyt zgodności per punkt. Otwiera segment Enterprise. | 4.0 |
| **Stolik widoczny w Google** (Reserve with Google) | Rezerwacja prosto z Map Google do widgetu Lokalo. Duży zasięg, ale proces certyfikacji Google — podjąć, gdy będzie >20 płacących lokali. | 3.3 |

## 4. Czego świadomie NIE robimy (i dlaczego)

- **Menu QR / strona www lokalu** (ocena 2.6–2.9, moat 1.0–2.3) — rynek zaorany przez darmowe
  narzędzia; zero wyróżnika. Wracamy najwyżej jako dodatek do Lejka opinii.
- **Zamówienia na wynos bez pośredników** (2.67) — wojna z Pyszne/Glovo wymaga marketingu
  konsumenckiego, którego solo-dev nie wygra. Zamiast tego: *rozliczenia* platform (pomysł #41 rankingu).
- **Karta lojalnościowa na pieczątki** (2.67) — commodity, niska wartość bez aplikacji konsumenckiej.
- **Moduł systemu kaucyjnego** (2.56) — czekamy, aż regulacje HoReCa się ustabilizują.
- **Gamifikacja załogi („Liga zmianowa")** (2.78) — ryzyko efektu cringe; wartość retencyjną
  dostarcza Portfel pracownika.

## 5. Rekomendowane „następne 3 rzeczy do zbudowania"

1. **Moduł „Zgodność lokalu"** — najtańszy compliance-win (S+M, feasibility 4.7–5.0),
   buduje wyłącznie na istniejącym (Web Push, strażnik grafiku, teczka pracownika),
   a przy kontroli sanepidu sprzedaje się sam.
2. **Skrzynka zapytań o imprezy z AI** — TOP 1 panelu (5.01), średni wysiłek, otwiera oś
   weselną i jest **najlepszym demo sprzedażowym**: „wklej maila → zobacz gotową odpowiedź
   z wolnymi terminami" robi efekt *wow* w 30 sekund.
3. **Portal klienta imprezy (etap 1)** — TOP 2 (4.93), M, domyka pętlę: zapytanie (AI) →
   karta imprezy → portal klienta → zadatki → obsada → rozliczenie. Po nim naturalnie
   etap 2 (Portal Pary Młodej) jako pierwszy **płatny add-on** Lokalo.

## 6. Zasady wykonania (niezmienne)

- **Budujemy NA istniejącym kodzie** — każdy pomysł wyżej wskazuje istniejący moduł-fundament;
  żadnych przepisywań od zera.
- **Jeden pas ruchu**: jedna funkcja na raz, w pełni + testy zielone + commit/push, potem następna.
- **Design system „Cicha scena"** (DESIGN.md) obowiązuje każdy nowy ekran.
- **Multi-tenant przed sprzedażą masową**: fundamenty (per-tenant sekrety, izolacja) trzymają
  priorytet z STRATEGIA-KOMERCJALIZACJI.md — funkcje z tej roadmapy nie mogą ich wyprzedzić
  kosztem bezpieczeństwa.

---

*Pełny ranking 64 pomysłów z ocenami panelu: artefakt sesyjny (ranking.json) — do wglądu na życzenie.*
