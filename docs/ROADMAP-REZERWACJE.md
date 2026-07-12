# Roadmapa rezerwacji Lokalo — samodzielny system operacyjny sali

> Status: kierunek zatwierdzony · R0a, R0b, R1a, R1b i R2.1 wdrożone · następny checkpoint R2.2 (sąsiedztwo i kanoniczne kombinacje) · 12 lipca 2026
>
> Zakres: administrator, manager, recepcja/host, publiczny widget, CRM i analityka
>
> Zasada wykonania: jeden pionowy etap naraz, testy i migracje przed kolejnym etapem

## 1. Decyzja produktowa

Rezerwacje mają działać jak samodzielny produkt wewnątrz Lokalo, a nie zbiór luźnych zakładek.
Jedno wejście ma obsługiwać cały cykl:

`konfiguracja lokalu → dostępność → rezerwacja → przydział stołu → obsługa wizyty → CRM → analiza`

Najważniejszy scenariusz operacyjny:

1. Recepcja odbiera telefon lub przyjmuje gościa.
2. Wybiera termin i liczbę osób.
3. System pokazuje dostępność oraz wyjaśnioną propozycję stołu lub kombinacji.
4. Recepcja zapisuje rezerwację bez opuszczania kontekstu dnia.
5. Dla grupy 18 osób system potrafi połączyć np. trzy sąsiadujące stoły, jeśli administrator
   dopuścił taką konfigurację.

### Zatwierdzone decyzje właściciela

- Roadmapa obejmuje również publiczny widget, komunikację, waitlistę, zadatki i wymagania RODO.
- Recepcja korzysta z nazwanych kont i ograniczonego trybu stanowiskowego; nie dostaje konta admina.
- „Recepcja/Host” jest presetem granularnych uprawnień, nie kolejną sztywną rolą domenową.
- Manager i recepcja mogą przekroczyć limit po ostrzeżeniu, świadomym potwierdzeniu i zapisaniu
  audytu. Szczegółowy wybór powodu należy do pełnego evaluatora R3/R4.
- Trwałe reguły ustawia administrator lub osoba z osobnym uprawnieniem do konfiguracji.
- Ręcznie przypisanej rezerwacji automat nie przenosi bez jawnej decyzji człowieka.
- Domyślny priorytet sal jest miękki; administrator może wybrać tryb ścisłego zapełniania kolejnego.

## 2. Wnioski z researchu rynku

Dojrzałe systemy rozdzielają fizyczną dostępność stołów od tempa przyjmowania nowych gości.
Jedno pole „ile rezerwacji jednocześnie” nie wystarcza.

| Wzorzec | Praktyka rynkowa | Decyzja dla Lokalo |
|---|---|---|
| Pacing | Resy łączy dostępność stołów z limitem coverów w krótkich oknach czasu | Osobny limit nowych rezerwacji i nowych osób na okno 15/30 min |
| Turn time | Czas wizyty zależy od wielkości grupy i serwisu | Progi 1–2, 3–4, 5–6, 7+ z możliwością własnej konfiguracji |
| Plan sali | Wiele planów, min./max. miejsc, typ stołu i dostępność kanałowa | Pierwszoklasowa encja sali oraz wersjonowany plan stołów |
| Kombinacje | Operator jawnie definiuje fizycznie możliwe zestawy | Graf sąsiedztwa + zatwierdzone kombinacje; nigdy dowolne łączenie |
| Priorytety | System optymalizuje stoły, ale operator steruje dostępnością i kolejnością | Strategie `preferuj`, `wypełniaj kolejno`, `balansuj`, `ręcznie` |
| Uprawnienia | Osobno zarządza się rezerwacjami, salą, regułami i nadpisaniami | Preset Recepcja oraz osobne uprawnienia operacyjne i konfiguracyjne |

Źródła pierwotne:

- [Resy — Availability and Pacing](https://helpdesk.resy.com/en_us/availability-and-pacing-updates-S1T3bPXLd)
- [Resy — Pacing by Floor Plan](https://helpdesk.resy.com/en_us/customizable-pacing-by-floorplan-SJGwJVqA)
- [Resy — Floor Plans and Table Combinations](https://helpdesk.resy.com/how-to-create-and-edit-floor-plans-in-the-resyos-app-Hk16bwXUO)
- [Eat App — Permissions and Conflict Preferences](https://restaurant.eatapp.co/knowledge/setting-up-permissions-and-preferences)
- [Eat App — Table Manager Views](https://restaurant.eatapp.co/features)
- [Tock — Table and Service Management](https://www.exploretock.com/join/restaurant-table-management-software/)
- [Tock — Table Combinations](https://tock.zendesk.com/hc/en-us/articles/15126385902612-Setting-up-Table-Combinations-for-Availability-Planning)
- [SevenRooms — Table Management](https://sevenrooms.com/platform/table-management/)
- [OpenTable — Availability Controls](https://www.opentable.com/restaurant-solutions/products/features/availability-controls/)
- [OpenTable — Guest Profiles](https://www.opentable.com/restaurant-solutions/resources/how-to-use-restaurant-guest-profiles/)

## 3. Stan obecny — co wykorzystujemy

Projekt ma więcej gotowych fundamentów, niż pokazuje obecny interfejs.

### Backend już posiada

- `GodzinyOtwarcia`: wiele serwisów dnia, długość slotu, turn time zależny od grupy oraz pacing.
- Globalną politykę online: wyprzedzenie, cutoff, min./max. grupa, bufor, anulowanie i auto-no-show.
- Stoliki z pojemnością, minimalną grupą, strefą, pozycją, kształtem, cechami, priorytetem i sekcją.
- Predefiniowane kombinacje stołów oraz graf sąsiedztwa.
- Silnik `seating.py`, który buduje kombinacje do czterech sąsiadujących stołów i ocenia kandydatów.
- Sugestie hosta, auto-przydział, kolejkę hosta, fazy wizyty, waitlistę, hold i reoptymalizację.
- CRM gości, historię rezerwacji, scoring no-show i analitykę.
- Wyjątki kalendarza: blackout oraz godziny specjalne.

### Frontend już posiada

- Dzienną bazę rezerwacji z formularzem, statusami, stolikami i waitlistą.
- Widok hosta z fazami `nadchodzący → przybył → posadzony → rachunek → wyszedł`.
- Plan sali drag-and-drop.
- Publiczny widget rezerwacyjny.
- CRM i analitykę rezerwacji.
- Dopracowany kontrakt interakcji w `RezerwacjeStolik`: lokalne aktualizacje, zachowane szkice,
  jawne pending/error, potwierdzenie destrukcji i przywracanie fokusu.

### Luki krytyczne przed rozbudową UI

1. Publiczny widget korzysta z prostszego wyboru pojedynczego stołu, a nie ze wspólnego silnika
   kombinacji i priorytetów.
2. Pacing dotyczy startów online; nie opisuje jeszcze całej jednoczesnej pojemności operacyjnej.
3. **Częściowo zamknięte w R2.1:** sala jest encją z własnym planem i kolejnością; strategia
   zapełniania oraz limity pozostają w R2.2/R3.
4. Plan sali nie zaznacza poprawnie wszystkich stołów dodatkowych kombinacji.
5. Priorytet zapisany na kombinacji nie wpływa dziś na ocenę kandydata.
6. `Stolik.laczy_sie` i graf sąsiedztwa tworzą dwa potencjalne źródła prawdy.
7. Edycja lub usunięcie stołu może pozostawić niespójne identyfikatory w polach JSON kombinacji.
8. **Zamknięte w R0b:** sprawdzenie dostępności i zapis są atomowe, a zasoby chroni ledger.
9. **Zamknięte w R1a:** manager/Recepcja wykonują operacje według granularnych praw zamiast roli admina.
10. `/api/rezerwacje` i `/api/me/rezerwacje` nadal mogą opierać się na legacy Google Calendar,
    zamiast na kanonicznej bazie `Termin`.
11. Ustawienia zaawansowane istnieją w API, lecz praktycznie nie istnieją w panelu.

## 4. Docelowa architektura informacji

W globalnej nawigacji pozostaje jedno wejście: `Goście → Rezerwacje`.

Wewnątrz powstaje `ReservationsWorkspace` z podwidokami zapisanymi w URL:

| Widok | Pierwsze pytanie użytkownika | Najważniejsza akcja |
|---|---|---|
| `Dzisiaj` | Kto zaraz przyjdzie i co dzieje się na sali? | `Dodaj rezerwację` |
| `Kalendarz` | Jak rozkładają się rezerwacje w wybranym dniu/tygodniu? | `Otwórz dzień` |
| `Baza rezerwacji` | Jak znaleźć i obsłużyć dowolną rezerwację? | `Wyszukaj` |
| `Sale i stoły` | Jak wygląda lokal i które stoły można łączyć? | `Edytuj plan` |
| `Dostępność` | Kiedy i na jakich zasadach przyjmujemy gości? | `Zapisz reguły` |
| `Analiza` | Co ogranicza sprzedaż i jak poprawić obrót? | `Zobacz rekomendację` |

CRM pozostaje osobnym obszarem `Goście`, ale karta rezerwacji otwiera dokładny profil gościa i po
powrocie zachowuje dzień, filtry, zaznaczenie i pozycję przewijania.

Na desktopie i tablecie widoczny jest pełny pasek podwidoków. Na telefonie recepcja widzi
`Dzisiaj`, `Kalendarz`, `Baza` i `Więcej`; konfiguracja, sale i analiza trafiają do `Więcej` i są
renderowane wyłącznie przy odpowiednich uprawnieniach.

Kontekst jest przechowywany jawnie:

- URL: podwidok, data/zakres, identyfikator rezerwacji i podstawowe filtry,
- pamięć sesji widoku: scroll, sortowanie i otwarty panel,
- bezpieczny draft: szybkie dodawanie i edycja,
- `returnTo`: kontrolowany powrót z CRM do dokładnego dnia i miejsca,
- wylogowanie, zmiana lokalu i blokada stanowiska: usunięcie PII i szkiców operatora.

Stan nie może przechodzić między operatorami tego samego urządzenia. Przycisk Wstecz odtwarza
poprzedni dzień, filtr, zaznaczenie oraz pozycję listy.

### Dostęp według profilu

| Profil | Domyślny ekran | Zakres |
|---|---|---|
| Administrator | Ostatni widok użytkownika; fallback `Dzisiaj` | Wszystkie widoki, konfiguracja, audyt i analityka |
| Manager | `Dzisiaj` | Operacje, baza, plan live, wyjątki dnia; trwałe reguły tylko z uprawnieniem |
| Recepcja/Host | `Dzisiaj` | Rezerwacje, host, waitlista, goście i przydział stołu; bez pozostałych modułów |
| Pracownik | Bez zmiany obecnego priorytetu roli | PII-safe agregat `/api/me/rezerwacje`; Rezerwacje pozostają dostępne po działaniach podstawowych |

## 5. Model dostępu i tryb stanowiska recepcji

Nie dodajemy kolejnej roli do rosnącego zestawu warunków w `role_guard`. Rozbudowujemy katalog
efektywnych uprawnień i dodajemy gotowy preset konta:

- `rezerwacje.podglad`
- `rezerwacje.operacje`
- `rezerwacje.host`
- `rezerwacje.nadpisuj_limity`
- `rezerwacje.sala`
- `rezerwacje.reguly`
- `rezerwacje.analityka`
- `rezerwacje.dane_kontaktowe`
- `rezerwacje.notatki_wewnetrzne`
- `rezerwacje.dane_wrazliwe`
- `rezerwacje.finanse`

Prawo `rezerwacje.eksport` powstanie dopiero razem z rzeczywistym eksportem bazy; nie dodajemy
martwego przełącznika, który sugerowałby administratorowi niedostępną funkcję.

Preset `Recepcja/Host` włącza: operacje, host, nadpisywanie limitów oraz dane kontaktowe
potrzebne do obsługi bieżącej rezerwacji. Notatki wewnętrzne i dane wrażliwe wymagają osobnych
uprawnień. Preset nie włącza konfiguracji sali, trwałych reguł, analityki ani eksportu.

Uprawnienie `rezerwacje.nadpisuj_limity` jest częścią zatwierdzonego presetu Recepcji. R1a egzekwuje
istniejące limity pacingu także w ścieżce ręcznej: pierwsza próba zwraca stabilne ostrzeżenie, a jawne
ponowienie przez uprawnione konto zapisuje kod `pacing_override` w audycie. Pełny evaluator wszystkich
reguł, wybór szczegółowego powodu i alternatywy zostają w R3/R4; UI nie może sugerować ich wcześniej.
Wpis R1a powstaje wyłącznie przy realnym przekroczeniu i zawiera typ reguły, stan przed operacją,
limit oraz wartość projekcyjną po operacji — bez tekstu swobodnego i bez danych gościa.

Odebranie uprawnienia działa w aktywnej sesji: odświeżony kontrakt uprawnień natychmiast maskuje
dane, zamyka nieuprawniony panel i pokazuje bezpieczny ekran odmowy także po wejściu z bezpośredniego
URL. Blokada stanowiska maskuje PII bez oczekiwania na następne odświeżenie.

### Nadpisywanie limitu

Przekroczenie limitu wymaga:

1. jasnego ostrzeżenia z nazwą naruszonej reguły,
2. wyboru lub wpisania powodu,
3. potwierdzenia operacji,
4. wpisu audytowego z użytkownikiem, czasem, starym limitem i wartością po nadpisaniu.

Nie stosujemy wspólnego hasła recepcji. Na współdzielonym urządzeniu tryb stanowiskowy pozwala
szybko przełączać nazwanych operatorów PIN-em. Blokada ekranu nie kończy bieżącego dnia, ale czyści
widoczne PII do czasu ponownego odblokowania.

## 6. Docelowy model domenowy

### 6.1 Sala rezerwacyjna

Nowa encja `SalaRezerwacyjna`:

- `id`, `nazwa`, `aktywna`, `kolejnosc`,
- `strategia`: `preferuj`, `wypelniaj_kolejno`, `balansuj`, `recznie`,
- `priorytet`,
- `online_aktywna`, `wewnetrzna_aktywna`,
- opcjonalne limity jednoczesnych coverów i rezerwacji,
- opcjonalny domyślny bufor,
- aktywny plan oraz domyślna data wejścia zmian w życie.

`Stolik.sala_id` staje się relacją. Dotychczasowe `Stolik.strefa` pozostaje przez okres migracyjny
jako fallback odczytu; backfill powstaje z istniejących nazw stref i `LokalConfig.sale`.

### 6.2 Stolik i plan

Stolik posiada:

- nazwę, salę, kolejność i aktywność,
- minimalną i maksymalną liczbę osób,
- kształt, rozmiar, obrót oraz pozycję,
- cechy (`okno`, `loża`, `dostępny dla wózka`, `wysoki`),
- dostępność `online`, `wewnętrzna`, `walk-in`,
- opcjonalny priorytet i sekcję kelnerską.

Wersjonowanie wymaga osobnych encji:

- `PlanSali` — plan należący do sali,
- `WersjaPlanu` — `draft/published/retired`, numer, `valid_from`, `valid_to`, autor,
- `PozycjaStolikaPlanu` — stabilny `stolik_id`, geometria i aktywność w danej wersji,
- wersjonowane krawędzie sąsiedztwa i kombinacje.

Edycja nie zmienia działającego serwisu, dopóki administrator nie wybierze `Opublikuj plan`.
Publikacja najpierw sprawdza wszystkie przyszłe rezerwacje. Usunięty lub zmieniony stół wymaga
mapowania na stabilny identyfikator, ręcznego rozwiązania konfliktu albo daty wejścia planu po
ostatniej przypisanej rezerwacji. Rollback przywraca poprzednią opublikowaną wersję bez zmiany
historycznych przypisań.

### 6.3 Sąsiedztwo i kombinacje

Jawna, opublikowana `KombinacjaStolow` jest kanonicznym zasobem, który może zostać zarezerwowany.
Graf sąsiedztwa pomaga edytorowi proponować i walidować kombinacje, ale runtime nie rezerwuje
dowolnego spójnego podgrafu. Administrator zatwierdza wygenerowane propozycje przed publikacją.
`Stolik.laczy_sie` zostaje zdeprecjonowane po migracji albo staje się wyłącznie uproszczonym
przełącznikiem UI pomocnym przy budowie grafu.

Kombinacja musi:

- zawierać co najmniej dwa różne stoły z tej samej sali,
- być spójna w grafie sąsiedztwa,
- mieć min./max. osób, priorytet i kanał (`online`, `wewnętrzna`, `oba`),
- blokować wszystkie stoły składowe w czasie rezerwacji,
- być możliwa do wyłączenia bez usuwania historii.

### 6.4 Serwis, czas wizyty i pojemność

Istniejące `GodzinyOtwarcia` ewoluuje w model serwisu rezerwacyjnego bez zrywania kompatybilności:

- dzień tygodnia, nazwa (`Lunch`, `Kolacja`), godziny,
- krok oferowanych terminów, np. 15 lub 30 minut,
- turn time według wielkości grupy,
- limit nowych rezerwacji w oknie,
- limit nowych osób w oknie,
- limit jednoczesnych rezerwacji i osób,
- opcjonalne limity per sala i kanał,
- zasady dużych grup (`online`, `do zatwierdzenia`, `tylko telefonicznie`).

Turn time jest czasem zajęcia zasobu, a krok slotu jest częstotliwością oferowanych godzin. Tych
pojęć nie wolno łączyć w jedno pole.

### 6.5 Audyt i atomowość

- Każdy zapis rezerwacji otrzymuje `created_by`, `updated_by`, kanał oraz historię istotnych zmian.
- Nadpisanie reguły zapisuje osobny rekord audytu z powodem.
- Sprawdzenie i rezerwacja zasobu odbywają się w jednej transakcji.
- Dla PostgreSQL używamy blokady odpowiednich zasobów/okien; dla SQLite w testach utrzymujemy
  deterministyczny mechanizm kompatybilny z pojedynczą instancją.
- Endpointy tworzące rezerwację przyjmują klucz idempotencji, aby podwójny klik lub retry sieci nie
  utworzył dwóch wpisów.

## 7. Jeden silnik dostępności

Publiczny widget, recepcja, manager, host i późniejsze integracje muszą korzystać z jednego serwisu
domenowego. Routery nie mogą samodzielnie wybierać stołu.

### Wejście

- data i preferowana godzina,
- liczba osób,
- kanał,
- preferowana sala/cechy,
- opcjonalna rezerwacja wyłączona z porównania podczas edycji,
- użytkownik i jego prawo do nadpisania.

### Pipeline

1. Walidacja polityki dnia, wyprzedzenia, cutoffu i dużej grupy.
2. Ustalenie serwisu, turn time oraz końca wizyty.
3. Ocena pacingu i jednoczesnej pojemności globalnej oraz per sala.
4. Pobranie pojedynczych stołów i jawnie opublikowanych kombinacji dostępnych w danym kanale.
5. Odrzucenie konfliktów, blokad, nieaktywnych zasobów i niedostępnych kanałów.
6. W trybie `wypelniaj_kolejno`: wybór pierwszej sali z bezpiecznym kandydatem przed scoringiem.
7. Ocena kandydatów; w trybie `preferuj` priorytet sali pozostaje miękkim składnikiem wyniku.
8. Atomowe zajęcie zasobu lub zwrócenie alternatyw.

### Kolejność oceny

1. Brak konfliktu i zgodność z twardymi regułami.
2. Najmniejsza liczba niewykorzystanych miejsc.
3. Ochrona dużych stołów przed małymi grupami.
4. Mniejsza liczba łączonych stołów.
5. Miękka strategia i priorytet sali; strategia ścisła została zastosowana wcześniej jako filtr.
6. Priorytet stołu/kombinacji.
7. Preferencje gościa i balans sekcji kelnerskich.

Wynik zawiera kodowane powody, nie tylko liczbę kosztu. UI może wtedy powiedzieć:

> S1 + S2 + S3 · 18 miejsc · stoły sąsiadują · preferowana Sala Główna · wolne do 20:30

### Brak wyniku

Silnik zwraca w tej kolejności:

1. najbliższe alternatywne godziny,
2. inną salę,
3. waitlistę,
4. rezerwację `do zatwierdzenia` dla uprawnionego operatora.

## 8. Publiczny widget

Docelowy przepływ:

`osoby → data → dostępne godziny → preferencja miejsca → dane → polityka/zadatek → potwierdzenie`

Wymagania:

- brak zaszytego limitu 20 osób; zakres wynika z reguł lokalu,
- duże grupy mogą przejść do zapytania lub rezerwacji do zatwierdzenia,
- tymczasowy hold slotu na czas końcowego formularza,
- alternatywne godziny i waitlista zamiast ślepego „brak miejsc”,
- ten sam silnik dostępności co panel,
- samodzielne potwierdzenie, anulowanie i — jeśli polityka pozwala — zmiana terminu,
- wiadomości SMS/e-mail i przypomnienia,
- zadatek, preautoryzacja lub brak płatności zależnie od polityki,
- informacja RODO oraz osobne, wersjonowane zgody marketingowe,
- alergie i dane szczególnej kategorii wyłącznie z właściwą podstawą, minimalizacją i retencją,
- data i godzina liczone w `Europe/Warsaw`, nie w UTC przeglądarki.

## 9. Roadmapa wykonawcza

Każdy etap jest osobnym, weryfikowalnym checkpointem. Nie rozpoczynamy kolejnego, jeśli kontrakt
bezpieczeństwa lub danych poprzedniego etapu nie jest domknięty.

### R0 — Uporządkowanie źródeł prawdy i testy regresji

**Cel:** zbudować bezpieczny fundament pod UI bez zmiany sposobu pracy użytkownika. R0 składa się
z dwóch osobnych checkpointów; oba muszą być zamknięte przed udostępnieniem zapisów recepcji.

#### R0a — Kanoniczne dane i integralność kombinacji

- Kanoniczną bazą rezerwacji staje się `Termin(rodzaj="stolik")`.
- Agregaty managera i pracownika przestają zależeć od legacy Google Calendar po kontrolowanym
  cutoverze; jest to zamierzona zmiana źródła danych, nie „niewidoczny refaktor”.
- Migracja dodaje `source_type` i `source_external_id` z unikalnością źródła, aby jednorazowy import
  wydarzeń Google/iCal był deduplikowalny.
- Narzędzie reconciliation porównuje przyszłe wpisy Google/iCal z `Termin`, generuje raport różnic
  i pozwala wykonać jednorazowy import przed datą odcięcia.
- Przed przełączeniem działa shadow-read za flagą: wynik kanoniczny jest porównywany z legacy, ale
  tylko `Termin` po zatwierdzonym cutoverze trafia do użytkownika. Nie utrzymujemy trwałego dual-write.
- Plan sali zaznacza wszystkie stoły kombinacji.
- Edycja ręcznego stołu czyści stary auto-przydział i dodatkowe stoły.
- Usuwanie stołu naprawia lub blokuje osierocenie kombinacji.
- Priorytet kombinacji trafia do silnika.

Testy:

- regresje dla edycji/usuwania kombinacji,
- połączone stoły zajęte w planie i osi czasu,
- import powtórzony dwa razy nie tworzy duplikatów,
- raport rozbieżności obejmuje rezerwacje historyczne i przyszłe,
- jeden agregat danych dla admina/managera/pracownika z redakcją PII po cutoverze,
- brak dostępu pracownika do pełnych danych gościa,
- regresja nawigacji i API: pracownik zachowuje bezpieczny widok rezerwacji po cutoverze.

**Done R0a:** data odcięcia i raport rozbieżności są jawne, przyszłe wpisy zostały uzgodnione lub
zaimportowane, a użytkownicy czytają kanoniczne `Termin` bez utraty rezerwacji.

#### R0b — Atomowy zapis, idempotencja i kontrakt dostępności

- Powstaje minimalny wspólny serwis sprawdzania dostępności dla istniejących zapisów.
- Sprawdzenie konfliktu i utworzenie rezerwacji są jedną operacją transakcyjną.
- Endpoint tworzenia przyjmuje klucz idempotencji i bezpiecznie zwraca wynik wcześniejszej próby.
- Tabela idempotencji ma unikalny klucz, fingerprint żądania, status i zapisany wynik; użycie tego
  samego klucza z inną treścią jest odrzucane.
- Zajęcie wielu stołów blokuje zasoby zawsze w rosnącej kolejności identyfikatorów, aby ograniczyć
  deadlocki. Trwały ledger blokad/pacingu jest jedynym źródłem prawdy dla transakcji.
- Kontrakt `availability result` opisuje naruszoną regułę, kandydatów i alternatywy.
- Publiczny i wewnętrzny zapis zachowują dotychczasowe reguły, ale nie mogą sprzedać tego samego
  stołu ani przekroczyć twardej pojemności w wyścigu.

Testy:

- dwa równoległe zapisy tego samego stołu,
- ponowienie tego samego żądania z kluczem idempotencji,
- konflikt limitu i konflikt stołu zwracają stabilne, rozróżnialne kody,
- zgodność SQLite w testach i docelowej transakcji PostgreSQL.

**Done R0b:** równoległe żądania nie tworzą podwójnej rezerwacji, a R1 może bezpiecznie otworzyć
zapisy managerowi i recepcji.

**Stan wdrożenia R0b — 11 lipca 2026:** checkpoint ukończony. Migracja `0051` tworzy trwały
ledger dni, minutowych zajęć stołów, pacingu i zaszyfrowanych wyników idempotencji. Ręczne i
publiczne tworzenie, edycja, statusy, host, waitlista, import cutover oraz zwalnianie zasobów
korzystają z jednej transakcji i deterministycznych blokad dni. Publiczny odczyt oraz zapis używają
tego samego silnika pojedynczych stołów i zatwierdzonych kombinacji, również dla grup 18-osobowych.
Klient webowy zachowuje klucz idempotencji przy ponowieniu po błędzie sieci. Anonimizacja RODO usuwa
także zaszyfrowany replay zawierający PII. Pełna regresja backendu, 173 testy frontendu i build
produkcyjny przechodzą. Test PostgreSQL jest gotowy i pozostaje warunkowy od `TEST_POSTGRES_URL`;
lokalnie wykonano wariant SQLite, a przed wdrożeniem produkcyjnym CI musi uruchomić oba silniki.

### R1 — Uprawnienia operacyjne i wspólny workspace

**Cel:** manager i recepcja mogą bezpiecznie wykonywać codzienną pracę.

R1 jest dostarczany jako dwa osobne checkpointy.

#### R1a — Recepcja, workspace i szybkie dodawanie

Backend:

- Rozdzielenie `rezerwacje.operacje`, `host`, `nadpisuj_limity`, `sala`, `reguly`, `analityka`.
- Egzekwowanie uprawnień na trasach zapisu, nie tylko ukrywanie przycisków.
- Preset konta `Recepcja/Host` oraz audyt dostępu do PII.
- Migracja transakcyjnej tabeli `ReservationAudit`; audyt operatora dla tworzenia, edycji i
  anulowania zapisuje się w tej samej transakcji co operacja. Nie używa best-effort logowania.

Frontend:

- `ReservationsWorkspace` z URL/deep-linkami.
- Workspace uruchamiany per lokal za flagą, z bezpiecznym powrotem do starego odczytu podczas R1.
- `Dzisiaj` oraz podstawowe wyszukiwanie jako pierwsza pionowa dostawa.
- Recepcja trafia bezpośrednio do `Dzisiaj` i nie widzi innych modułów.
- Szybkie dodawanie najpierw wyszukuje istniejącego gościa po telefonie/e-mailu i pokazuje minimum:
  wcześniejsze wizyty, no-show, preferencję miejsca i dozwolone notatki.
- Desktop/tablet używa prawego panelu szybkiego dodawania; mobile krótkiego widoku pełnoekranowego.
- Kolejność: termin i osoby → dostępność → rekomendacja → dane gościa → zapis.
- Po zapisie rezerwacja pojawia się w miejscu i otrzymuje fokus; błąd zachowuje cały szkic.
- Utrata proponowanego slotu pokazuje alternatywy bez zerowania formularza.
- Zachowanie dnia, filtrów, zaznaczenia, szkicu i scrolla.

Testy:

- macierz uprawnień admin/manager/recepcja/pracownik,
- próby bezpośredniego wywołania chronionych endpointów,
- natychmiastowe odebranie PII i bezpieczny ekran odmowy po zmianie uprawnienia,
- pełny przepływ klawiaturą oraz mobile/tablet/desktop.

**Done R1a:** recepcja dodaje rezerwację od początku do widocznego zapisu bez opuszczenia kontekstu
dnia, bez utraty szkicu i bez pełnego przeładowania listy. Nie ma dostępu do finansów, grafiku ani
ustawień lokalu.

**Stan wdrożenia R1a — 12 lipca 2026:** nazwane konto `szef` może otrzymać atomowy preset
`recepcja_host` bez tworzenia nowej roli. Backend egzekwuje dokładną macierz metoda+trasa, odświeża
prawa z bazy przy każdym żądaniu, redaguje kontakt/notatki/finanse/dane zdrowotne oraz ponownie
renderuje replay idempotencji według bieżących praw. Migracja `0052` dodaje transakcyjny,
pozbawiony PII `ReservationAudit`; audyt obejmuje operacje użytkownika, hosta, gościa online,
reoptymalizację systemową, import cutover i anonimizację RODO. Workspace Recepcji otwiera tylko
`Rezerwacje dzisiaj` i `Host`, zachowuje szkic po błędzie, aktualizuje rekord w miejscu i nie pokazuje
ustawień sali, notatek, finansów ani twardego DELETE. Pacing ręczny wymaga ostrzeżenia i jawnego
ponowienia, a audyt opisuje wyłącznie rzeczywiście przekroczoną regułę. Atomowe `posadz` usuwa
częściowy sukces dwóch osobnych zapisów hosta. Oba widoki unieważniają stare odpowiedzi po zmianie
dnia, zamykają formularz po zmianie praw PII i odróżniają awarię od pustej sali. Pełna regresja
backendu przeszła przed finalnym hardeningiem migracji, a po nim przechodzi 55/55 testów wszystkich
dotkniętych modułów; frontend ma 190/190 testów i zielony build produkcyjny. Test współbieżności
PostgreSQL pozostaje warunkowy od `TEST_POSTGRES_URL`. R1b przejmuje teraz kalendarz, bazę,
wyszukiwanie gościa, deep-linki i pamięć kontekstu.

#### R1b — Kalendarz, baza rezerwacji i ciągłość

- Widok `Kalendarz` dzień/tydzień z agendą zajętości i szybkim przejściem do dnia. Do czasu pełnego
  evaluatora R3/R4 puste miejsce nie jest nazywane „wolnym slotem”.
- Podstawowa `Baza rezerwacji`: wyszukiwanie po nazwisku/telefonie, statusie i zakresie dat.
- URL przechowuje podwidok, datę, podstawowe filtry i wybraną rezerwację.
- Pamięć sesji przechowuje scroll, sortowanie i otwarty panel osobno dla użytkownika/lokalu.
- `returnTo` prowadzi z CRM do dokładnego miejsca; Back odtwarza poprzedni kontekst.
- Wylogowanie, zmiana lokalu i blokada stanowiska usuwają PII oraz szkice operatora.

**Done R1b:** przejście między dniem, bazą i kartą gościa nie zeruje kontekstu ani nie przenosi
stanu między operatorami wspólnego urządzenia.

**Stan wdrożenia rdzenia R1b — 12 lipca 2026:** administrator, manager i preset Recepcja/Host
korzystają z jednego `ReservationsWorkspace`; stare osobne wejścia `Rezerwacje stolików` i `Host`
zostały scalone. Workspace ma działające podwidoki `Dzisiaj`, `Kalendarz`, `Baza` i opcjonalny
`Host`, filtrowane bieżącymi uprawnieniami. Namespacowany hash URL przechowuje wyłącznie bezpieczny
kontekst (widok, daty, status, sort, offset i opaque ID), nie koliduje z publicznymi parametrami
aplikacji i obsługuje reload oraz Back/Forward. Wpisy historii są oznaczone instancją i operatorem;
powrót do wpisu innego użytkownika jest kanonizowany przed pobraniem PII.

Backend udostępnia redagowany detail po ID oraz ograniczone do 366 dni, paginowane wyszukiwanie
POST po nazwisku/telefonie, statusie i zakresie. Fraza PII pozostaje w body i pamięci aktywnego
widoku — nigdy w URL ani session storage. Kalendarz i Baza unieważniają stare requesty oraz nie
pokazują starego snapshotu pod nową datą lub filtrem. Deep-link z samym ID odnajduje aktualny dzień
rekordu. Kontekst nie-PII i scroll są pamiętane osobno dla użytkownika/instancji, także po
doładowaniu dłuższej treści. Wylogowanie, 401 i zmiana instancji czyszczą pamięć, trasę oraz szkice
komponentów. Wszystkie operacyjne daty „Dzisiaj” używają `Europe/Warsaw`.

**Stan wdrożenia R1b.2 — 12 lipca 2026:** checkpoint R1b jest zamknięty. Karta gościa otwiera się
wyłącznie przez nieosobowy `reservation_id`; lista CRM zwraca `profil_ref`, a aktywny frontend nie
wysyła telefonu, e-maila, nazwiska ani ich hasha w ścieżce API. Osoby bez telefonu i e-maila nie są
już łączone po samym nazwisku — profil i historia pozostają wtedy ograniczone do jednej rezerwacji.
Backend redaguje dane wrażliwe i notatki według granularnych praw, pozostawia zapis profilu
administratorowi oraz oznacza przestrzenie odpowiedzi PII (także RODO i terminy) jako
`private, no-store`. Profil ma pełny lifecycle: po dopisaniu, korekcie lub usunięciu kontaktu
jest migrowany tylko wtedy, gdy stara tożsamość nie opisuje innych wizyt, oraz scalany bez utraty
alergii/notatek i bez wskrzeszania zgody marketingowej,
a usunięcie rekordu albo anonimizacja RODO usuwa fallback przed możliwym ponownym użyciem ID.
Zmiana granularnych praw lub roli aktywnego konta aktualizuje snapshot autoryzacji między kartami,
natychmiast redaguje otwartą kartę i dopiero potem pobiera jej bezpieczną wersję ponownie.

Profil jest jednym routowanym dialogiem nad nadal zamontowanym workspace. `Back`, Escape i
„Wróć do rezerwacji” odtwarzają dokładny dzień, zaznaczenie, filtry, scroll, fokus i bezpieczny
szkic aktywnego operatora; parametr `gosc` zawiera wyłącznie ID rezerwacji. Historia przeglądarki
ma teraz actor + losowy privacy epoch. Epoch rotuje po jawnym logowaniu, wylogowaniu, 401, zmianie
instancji i `423 WORKSTATION_LOCKED`, więc stary wpis tego samego operatora jest odrzucany przed
pobraniem PII. Jeden purge czyści URL, pamięć tras i sesji rezerwacji, wyniki, formularze, aktywne potwierdzenia
i cache komponentów, abortuje odczyty oraz mutacje i propaguje się między kartami. Spóźnione 401/423
starego bearer tokenu nie mogą wylogować ani zablokować nowego operatora. Blokada 423 ma lokalny
one-shot latch: odmontowuje powierzchnie operacyjne i pozwala tylko jawnie sprawdzić sesję ponownie
lub się wylogować, bez pętli requestów. Brudny profil chroni także Browser Back i odświeżenie.
R1b.2 dostarcza ten kontrakt bezpieczeństwa, ale nie pozorny PIN: właściwa sesja operatora,
revokacja, rate limit i audyt PIN-u pozostają osobnym etapem.

### R2 — Sale i publikowany plan stołów

**Cel:** administrator opisuje prawdziwy układ lokalu i możliwe połączenia.

**Stan wdrożenia (12 lipca 2026):** R2.1 jest ukończone. Dostarcza pierwszoklasowe sale,
`Stolik.sala_id` z kontrolowanym fallbackiem `strefa`, migracje 0053–0054 z bezpiecznym
backfillem, round-tripem i Unicode-safe kluczem nazw sal, dokładnie jeden plan na salę, wersje
`draft/published/retired`, optimistic revision,
pełny snapshot pozycji oraz atomową publikację współdzielącą blokady z rezerwacjami i holdami.
Konfiguracja jest częścią `ReservationsWorkspace`; obsługuje wiele sal, dodawanie nieaktywnego
stołu do szkicu, drag, klawiaturę i pola geometrii, jawny zapis/publikację/odrzucenie, zachowanie
lokalnych zmian także przy wyjściu z workspace, retry właściwej operacji, konflikty między kartami,
stałe proporcje planu na różnych ekranach i konto `floor-only`.
Stary modal bezpośredniej edycji stolików w planie dnia został zastąpiony jednym przejściem
`Konfiguruj sale`, aby wszystkie zmiany układu przechodziły przez szkic i publikację.
Operacyjny plan czyta wyłącznie opublikowane pozycje i opisuje fakty (`bez_rezerwacji`, hold,
rezerwacja, POS), bez obietnicy dostępności przed R3/R4.

R2 nie jest jeszcze zamknięte. R2.2 ma dodać wersjonowane krawędzie sąsiedztwa i kanoniczne
kombinacje, właściwości stołów w snapshotach, tryb „Połącz stoły”, sprawdzian grupy 18-osobowej,
undo/redo, przyciąganie i wyrównywanie oraz strategię/priorytet sal. Nie należy udawać tych
możliwości na podstawie legacy `lacze_sie`, `sasiedztwo` lub `KombinacjaStolow`.

Backend/migracja:

- `SalaRezerwacyjna`, `Stolik.sala_id`, strategia i priorytet sali.
- Backfill z `strefa`/`LokalConfig.sale`, fallback odczytu i test migracji na świeżej bazie.
- Wersja robocza/opublikowana planu.
- Walidacja tej samej sali i spójności grafu dla kombinacji.

Frontend:

- Lista sal i przełączanie planu.
- Dodawanie, pozycjonowanie, obrót, rozmiar i właściwości stolika.
- Tryb `Połącz stoły`: wskazanie sąsiedztwa i podgląd możliwych grup.
- Panel sprawdzający: „dla 18 osób dostępne są S1+S2+S3”.
- Jawne `Zapisz szkic` oraz `Opublikuj plan`.
- Undo/redo, przyciąganie, wyrównywanie oraz tekstowe statusy niezależne od koloru.
- Alternatywa dla drag-and-drop: pola X/Y, rozmiar/obrót i przesuwanie strzałkami z ogłoszeniem
  nowej pozycji. Telefon oferuje podgląd i edycję właściwości; pełna geometria jest kierowana na
  tablet/desktop, ale pozostaje dostępna formularzowo.

Testy:

- backfill i rollback migracji,
- brak połączeń między salami,
- zapis/odrzucenie szkicu, konflikt wersji i zachowanie niezapisanych zmian,
- publikacja przy przyszłej rezerwacji na usuwanym stole: blokada, mapowanie lub data wejścia,
- klawiatura, dotyk i długi tekst nazw sal.

**Kryterium zamknięcia całego R2:** administrator potrafi odwzorować wiele sal i zweryfikować fizycznie możliwe kombinacje
bez wpływania na działający serwis przed publikacją.

### R3 — Reguły dostępności, serwisy i symulator

**Cel:** wszystkie zasady można ustawić bez znajomości terminologii systemowej.

Backend/migracja:

- Rozdzielenie historycznego `dlugosc_slotu_min` na `krok_slotu_min` i
  `domyslny_turn_time_min`; backfill ustawia oba pola z dotychczasowej wartości.
- Tabele/pola nadpisań reguł per sala i kanał oraz trwałe bucket’y limitów jednoczesnych.
- Wspólny evaluator reguł rozszerza minimalny kontrakt R0b i działa również dla zapisów ręcznych.
- Nadpisanie przez managera lub recepcję zapisuje transakcyjny `ReservationAudit` z regułą,
  wartością, powodem i użytkownikiem.

Frontend `Dostępność`:

- kreator serwisów: Lunch/Kolacja, dni, godziny i krok terminów,
- czasy wizyt według liczby osób,
- limit nowych rezerwacji i osób na okno,
- limit jednoczesnego obłożenia,
- bufory, duże grupy, wyprzedzenie i cutoff,
- reguły globalne z opcjonalnym nadpisaniem per sala/kanał,
- wyjątki konkretnego dnia i zamknięcia,
- podgląd reguł: „Sobota 18:00, 18 osób — które limity zadziałają?”. Pełna symulacja przydziału
  stołów i strategii sali powstaje w R4 na docelowym silniku.
- lokalny panel nadpisania: nazwa reguły, limit i wartość po operacji, gotowe powody, opcjonalna
  notatka oraz jedno jawne potwierdzenie.

UX:

- tryb prosty z dobrymi wartościami startowymi,
- `Ustawienia zaawansowane` dopiero na żądanie,
- podgląd wpływu przed zapisem,
- ostrzeżenie przed regułą, która zamknie całą sprzedaż online.

Testy:

- granice okien pacingu i nakładających się wizyt,
- reguły globalne/per sala/per kanał,
- ostrzeżenie + powód + audyt nadpisania dla managera i recepcji,
- DST i `Europe/Warsaw`,
- wyjątki świąteczne,
- zachowanie dotychczasowych lokali po migracji.

**Done:** administrator sam konfiguruje politykę, a podgląd reguł korzysta z tego samego ewaluatora
co ręczne i publiczne API. Pełna rekomendacja konkretnego stołu pozostaje bramką R4.

### R4 — Wspólny silnik alokacji 2.0 i atomowość

**Cel:** panel i widget nigdy nie sprzedają tego samego zasobu ani nie podejmują sprzecznych decyzji.

Zakres:

- Ekstrakcja wspólnego serwisu dostępności z routerów.
- Nowy silnik działa najpierw w shadow mode za flagą: porównuje decyzje ze starą ścieżką bez
  przydzielania zasobu, raportuje różnice i dopiero potem przejmuje zapis.
- Publiczny widget, recepcja, edycja i host używają tego samego pipeline’u.
- Strategie sal jako proste polityki operatora; wewnętrzne, wersjonowane wagi nie są wystawiane
  administratorowi jako surowe liczby.
- Manualne przypisanie jako twarda blokada dla reoptymalizacji.
- Powody wyboru i alternatywy w kontrakcie API.
- Rozszerzenie ledgera R0b o wiele stołów, bucket’y pacingu, kolejność blokad i ochronę przed
  deadlockiem.
- Zajętość live, walk-in i hold uczestniczą w tym samym modelu blokad; POS jest opcjonalnym źródłem
  stanu, a brak POS nie wyłącza ręcznego toru.
- Pełny symulator administratora korzysta z dokładnie tego samego silnika i pokazuje powody wyboru.

Scenariusze odbiorowe:

- 18 osób → trzy sąsiadujące stoły w preferowanej sali.
- Zajęcie jednego składnika → kombinacja odpada.
- Mniejsza grupa nie blokuje jedynego dużego stołu, jeśli istnieje lepszy kandydat.
- Tryb ścisły zapełnia Salę Główną przed Ogrodem.
- Tryb miękki odchodzi od priorytetu, gdy inaczej zablokowałby dużą grupę.
- Dwa jednoczesne żądania nie rezerwują tego samego stołu i nie przekraczają limitu.

**Done:** wszystkie kanały korzystają z jednego silnika i bezpiecznie zapisują tylko jeden wynik,
ale zwracają dostępność właściwą dla reguł swojego kanału. Widget nie ujawnia zapasu
zarezerwowanego dla telefonu, walk-in lub obsługi wewnętrznej.

### R5 — Publiczny widget, komunikacja, zadatki i RODO

**Cel:** gość może bezpiecznie zakończyć pełny proces bez telefonu do lokalu.

R5 jest dostarczany w trzech osobnych checkpointach o różnych ryzykach.

#### R5a — Widget, hold, tokeny i RODO

- Nowy widget i jego inventory są uruchamiane per lokal/kanał za osobną flagą.
- Nowy przepływ widgetu, alternatywne godziny i waitlista.
- Duże grupy jako rezerwacja, zapytanie lub wpis do zatwierdzenia według polityki.
- `ReservationHold` obejmuje wszystkie stoły kombinacji, ma TTL, właściciela sesji, stan i jawne
  zwolnienie po wygaśnięciu/anulowaniu.
- Limit aktywnych holdów per klient/IP i rate limit tras publicznych zapobiegają blokowaniu zapasu.
- Token zarządzania rezerwacją jest przechowywany wyłącznie jako hash i posiada `expires_at`,
  `used_at`, zakres operacji oraz rotację po użyciu.
- Migracja unieważnia lub bezpiecznie obraca istniejące wielokrotnego użytku tokeny plaintext;
  nie kopiujemy ich do nowego modelu w jawnej postaci.
- Potwierdzenie, zmiana i anulowanie korzystają z idempotentnych operacji.
- Informacja RODO, wersjonowane zgody, retencja i eksport/usunięcie danych.
- Odmowa zgody marketingowej nie blokuje rezerwacji; dane wrażliwe mają osobny kontrakt.
- Publiczne trasy są wpisane jako dokładne pary `endpoint + metoda`; nie używamy ogólnej publicznej
  zgody dla całego prefiksu `/api/online`.

Testy:

- E2E happy path i wszystkie warianty braku miejsca,
- wygaśnięcie/zwolnienie holda oraz limit nadużyć,
- wygasły, użyty i obrócony token,
- negatywne testy nieznanej trasy/metody pod `/api/online`,
- odmowa zgody marketingowej i redakcja danych wrażliwych,
- mobile 390×844, czytnik ekranu i brak poziomego overflow.

**Done R5a:** publiczna dostępność respektuje reguły kanału, a rezerwacja nie może zablokować zasobu
na zawsze ani ujawnić tokenu w bazie.

#### R5b — Komunikacja i outbox

- Transakcyjny outbox wiadomości oraz scheduler niezależny od żądania HTTP.
- Osobne próby dostarczenia, retry z backoffem, reconciliation i status widoczny operatorowi.
- Gdy provider obsługuje klucz idempotencji, używamy go w każdej próbie. Dla SMTP/providera bez
  takiego kontraktu przyjmujemy semantykę co najmniej raz i jawnie obsługujemy możliwy duplikat po
  awarii między przyjęciem wiadomości a zapisem potwierdzenia.
- Szablony potwierdzenia, przypomnienia, zmiany, anulowania i „stolik gotowy”.
- Preferencje kanału, rezygnacja z komunikacji marketingowej i audyt wiadomości operacyjnych.
- Awaria SMTP/SMS nie cofa poprawnie zapisanej rezerwacji.

**Done R5b:** każda wiadomość ma odtwarzalny stan; provider z idempotencją nie dostaje duplikatu,
a dla kanału co-najmniej-raz system wykrywa niepewny wynik i pozwala go uzgodnić bez ślepego retry.

#### R5c — Zadatki i preautoryzacja

- Etap zależy od zweryfikowanej integracji płatniczej opisanej w `docs/ROADMAP-MONETYZACJA.md`.
- Polityka płatności per serwis, grupa i dzień.
- Stany: `niewymagana`, `oczekuje`, `autoryzowana`, `oplacona`, `nieudana`, `wygasla`, `zwrocona`.
- Webhook z weryfikacją podpisu, idempotencją zdarzeń i bezpiecznym retry/refundem.
- Nieudana płatność zwalnia hold lub proponuje powrót do płatności zgodnie z jawną polityką.
- SCA/3DS i preautoryzacja są delegowane certyfikowanemu providerowi; Lokalo nie przechowuje danych
  karty ani CVC.

**Brama produkcyjna:** sandbox służy wyłącznie do demonstracji. R5c nie jest produkcyjnie gotowe
bez prawdziwego providera, zweryfikowanych webhooków i E2E płatność–zwrot.

**Done R5c:** zadatek i zwrot są spójne z rezerwacją, audytowalne i przetestowane na prawdziwym
środowisku testowym providera.

### R6 — Tryb stanowiska hosta

**Cel:** ekran żyje wraz z serwisem i ogranicza liczbę decyzji recepcji.

#### R6a — Tożsamość operatora i blokada stanowiska

- Nazwane konto i zwykłe logowanie z R1 pozostają bezpiecznym fallbackiem.
- Osobny model poświadczenia PIN przechowuje wyłącznie mocny hash, liczbę prób i czas blokady.
- Krótka sesja operatora jest związana z zarejestrowanym stanowiskiem, ma reautoryzację i jawne
  unieważnienie po dezaktywacji konta lub zmianie uprawnień.
- Rate limit, narastająca blokada i audyt prób chronią przed zgadywaniem PIN-u.
- Automatyczna blokada natychmiast maskuje PII; odblokowanie przywraca wyłącznie kontekst danego
  operatora, nigdy szkic poprzedniej osoby.

**Done R6a:** przełączenie operatora zachowuje audyt osoby wykonującej operację i nie pozwala
przejąć aktywnej sesji prostym odgadnięciem PIN-u.

#### R6b — Zaawansowany host stand live

- zsynchronizowany plan live, lista i oś czasu,
- lokalne statusy akcji, bez pełnego przeładowania tablicy,
- timery wizyt i czytelne opóźnienia,
- drag-and-drop z pełną walidacją oraz alternatywą klawiaturową,
- waitlista ze stanami `oczekuje`, `zaoferowano`, `zaakceptowano`, `wygasla`, `anulowano`,
- priorytet/kolejność waitlisty, czas ważności oferty, hold wszystkich stołów, audyt powiadomień
  oraz automatyczne zwolnienie po wygaśnięciu,
- tryb offline: ostatnie dane tylko do odczytu, kolejka zapisu dopiero po osobnej analizie konfliktów.

Aktualizacje live nie ogłaszają całej tablicy czytnikowi ekranu. `aria-live` obejmuje wyłącznie
wynik konkretnej akcji; timery nie generują cyklicznych komunikatów.

**Done R6b:** host prowadzi cały serwis z jednego widoku, a każda akcja daje lokalny i odwracalny tam,
gdzie to bezpieczne, feedback.

### R7 — CRM, analiza i rekomendacje

**Cel:** dane z rezerwacji poprawiają kolejne decyzje, ale automat nie zmienia polityki bez zgody.

Zakres:

- rozwinięcie podstawowej bazy R1b o pełnotekstowe filtry, historię, kontrolowany eksport i
  narzędzia jakości danych,
- łączenie duplikatów gości oraz wersjonowane zgody,
- rzeczywiste turn times z `host_seated_at`/`host_left_at`,
- wykorzystanie sal, stołów i kombinacji,
- odrzucony popyt, przyczyny braku dostępności i skuteczność waitlisty,
- rekomendacje: „grupy 1–2 siedzą zwykle 82 min; ustawione 120 min”,
- symulacja wpływu rekomendacji przed jej zastosowaniem.

**Done:** administrator rozumie, dlaczego traci dostępność, i może świadomie przyjąć lub odrzucić
konkretną zmianę reguły.

### R8 — Hardening i rollout

**Cel:** bezpieczne uruchomienie na istniejących lokalach.

- Finalne sterowanie flagami workspace’u, silnika i widgetu wprowadzonymi odpowiednio w R0/R1,
  R4 i R5; R8 odpowiada za ich rollout i usunięcie ścieżek tymczasowych, nie za późne dodanie flag.
- Migracja próbna na kopii danych oraz porównanie dostępności starej i nowej ścieżki.
- Logowanie decyzji silnika bez zapisywania zbędnego PII.
- Monitoring konfliktów, nadpisań, 409/422, czasu odpowiedzi i niedostarczonych wiadomości.
- Plan powrotu do poprzedniego UI/silnika bez cofania migracji danych; fallback nadal czyta
  kanoniczne `Termin` i nigdy nie przywraca Google Calendar jako źródła prawdy.
- QA admin/manager/recepcja/public, desktop/tablet/mobile, długie dane, offline i błędy.

**Done:** rollout jest stopniowy, mierzalny i odwracalny bez utraty rezerwacji.

## 10. Zależności i kolejność

```text
R0a dane + integralność
 └─ R0b atomowość + idempotencja
     └─ R1a Recepcja + Dzisiaj
         └─ R1b Kalendarz + Baza rezerwacji
             ├─ R2 sale + wersjonowany plan
             │   └─ R3 dostępność + reguły
             │       └─ R4 wspólny silnik + strategie
             │           ├─ R5a widget + RODO
             │           │   ├─ R5b komunikacja → R5c płatności
             │           │   └─ R8 rollout bazowy (R4 + R5a)
             │           ├─ R6a bezpieczny PIN → R6b host stand live
             │           └─ R7 CRM + analiza
             └─ podstawowy CRM z R1 pozostaje dostępny
```

R1 może rozpocząć budowę wspólnej powłoki i operacji dopiero po R0b. Konfigurator sal nie może
udawać pełnej automatyzacji przed R2–R4. `rezerwacje.nadpisuj_limity` jest widoczne w modelu
uprawnień wcześniej, lecz realne nadpisanie działa dopiero po evaluatorze R3.

R8 bazowo wymaga R4 i R5a. Jeżeli konkretny rollout obejmuje komunikację, płatności, PIN, host stand
lub rekomendacje, musi dodatkowo czekać odpowiednio na R5b, R5c, R6a, R6b lub R7. R7 nie jest
samodzielną bramką wdrożenia widgetu ani silnika.

## 11. Pierwszy batch do wdrożenia

Najbezpieczniejszy pierwszy checkpoint to **R0a — Kanoniczne dane i integralność kombinacji**.

Proponowany zakres jednego PR/commita:

1. Test regresji: kombinacja zajmuje wszystkie stoły na planie.
2. Naprawa planu sali dla `stoliki_dodatkowe`.
3. Test i naprawa edycji rezerwacji: ręczny stół czyści poprzednią kombinację i flagę auto.
4. Test i bezpieczna obsługa usuwania stołu użytego w kombinacji.
5. Podłączenie `KombinacjaStolow.priorytet` do oceny silnika.
6. Migracja identyfikatora źródła oraz narzędzie raportu/importu legacy z testem idempotencji.
7. Flaga shadow-read i raport różnic przed wyznaczeniem daty cutoveru.

Ten batch jest weryfikowalny i usuwa błędy, które byłyby bardzo trudne do diagnozowania po
zbudowaniu nowego UI. Bezpośrednio po nim powstaje osobny checkpoint R0b z atomowym zapisem oraz
idempotencją; dopiero wtedy wolno rozpocząć R1a.

## 12. Bramka jakości każdego etapu

Każdy etap musi przejść odpowiednie dla dostarczanej w nim funkcji bramki. Nie wymagamy scenariusza
z kombinacją przed powstaniem modelu sal, ale od momentu dostarczenia danej możliwości test staje
się obowiązkowy dla każdego kolejnego etapu.

- skupione testy backendu i frontendu,
- test migracji w górę i w dół na świeżej bazie,
- macierz uprawnień i bezpośrednie próby API,
- realistyczne dane: pusto, typowo, duży ruch, długie nazwy, duża grupa,
- jawne stany per podwidok: pierwsze ładowanie, odświeżanie z zachowaniem treści, pusty stan,
  częściowa awaria, dane nieaktualne/offline, pending/retry, 409, 422, wygaśnięcie holda, odebrane
  uprawnienie, blokada PII, read-only subskrypcji oraz konflikt publikacji,
- klawiaturę, nazwy dostępnościowe, focus i cele 44 px,
- 390×844, 768×1024, tablet landscape i mały desktop 1366×768,
- brak utraty dnia, filtrów, szkiców i pozycji przewijania,
- produkcyjny build frontendu,
- czystą konsolę aplikacji,
- od R2/R4: ręczny scenariusz 18 osób na trzech zatwierdzonych, sąsiadujących stołach,
- od R0b: test współbieżności rezerwacji tego samego zasobu.

Nie uznajemy etapu za zakończony na podstawie samego wyglądu lub pojedynczego happy path.

## 13. Metryki produktu i operacji

Najpierw zbieramy baseline, później ustalamy progi. Mierzymy:

- czas dodania rezerwacji telefonicznej,
- udział auto-przydziałów zaakceptowanych bez zmiany,
- liczbę ręcznych nadpisań i ich powody,
- odrzucony popyt według godziny, grupy i sali,
- wykorzystanie miejsc i liczbę obrotów stołu,
- różnicę ustawionego i rzeczywistego turn time,
- skuteczność waitlisty,
- no-show i anulowania,
- konflikty zapisu i ponowienia,
- dostarczalność wiadomości.

Metryki nie mogą zawierać numeru telefonu, e-maila, alergii ani pełnego nazwiska.

## 14. Świadome non-goals

- Nie przywracamy Google Calendar jako źródła rezerwacji.
- Nie tworzymy osobnego algorytmu dla widgetu, hosta i managera.
- Nie dodajemy współdzielonego konta bez audytu operatora.
- Nie łączymy stołów z różnych sal lub bez fizycznego sąsiedztwa.
- Nie pozwalamy automatowi ruszać ręcznych przypisań.
- Nie zmieniamy turn time automatycznie na podstawie analityki.
- Nie ukrywamy przekroczeń limitu; każde wymaga powodu i audytu.
- Nie budujemy dekoracyjnego planu 3D przed poprawnym modelem danych i dostępnością.
- Nie mieszamy konfiguracji trwałej z ekranem codziennej pracy recepcji.

## 15. Następna decyzja wykonawcza

R0a, R0b, R1a, R1b i R2.1 są zamkniętymi checkpointami. Następny milestone to `R2.2`:
wersjonowane sąsiedztwo, kanoniczne kombinacje, właściwości stołów i narzędzia edytora. Nie rozszerzamy jeszcze
pełnego ewaluatora R3/R4; korzysta on z gotowych granic uprawnień, audytu i atomowości dopiero w
swoim etapie. Serwerowa blokada stanowiska z sesją operatora i PIN-em pozostaje oddzielnym zadaniem,
którego nie wolno udawać samą zasłoną frontendu.
