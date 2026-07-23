# Wdrożenie produkcyjne modułu rezerwacji

Rezerwacje mają jedno źródło prawdy: bazę Lokalo i rekordy `Termin(rodzaj="stolik")`.
Tryby `legacy`, `shadow` oraz odczyt z Google Calendar zostały wycofane. Nie należy
ich przywracać jako awaryjnego źródła danych, ponieważ ponownie utworzyłoby to dwa
rozbieżne kalendarze.

## Zakres gotowy bez zewnętrznych dostawców

- ręczne rezerwacje, host, widok sali i lista oczekujących,
- reguły, limity, wyjątki, priorytety sal i konfiguracje łączonych stołów,
- publiczny widget v2 z sesją, holdem, idempotencją i wersjonowanymi zgodami,
- CRM gości, historia, jakość danych, kontrolowany eksport i odwracalne scalanie,
- analityka, rekomendacje, symulacja oraz jawna decyzja operatora,
- konta Recepcja / Host i szczegółowe uprawnienia,
- lokalny sandbox zadatków wyłącznie w środowisku deweloperskim.

## Świadomie wyłączone bramki zewnętrzne

Nie blokują one funkcjonalnego domknięcia ani ręcznej obsługi rezerwacji. Każda z nich blokuje
jednak aktywację zależnej funkcji albo końcowy odbiór produkcyjny:

- SMTP i SMS — do czasu podania danych wybranego dostawcy,
- Stripe — do czasu założenia działalności i konta Stripe,
- produkcyjna treść informacji RODO — do zatwierdzenia przez właściciela danych
  lub prawnika,
- końcowe testy współbieżności — na docelowej bazie PostgreSQL,
- instalacja PWA i ergonomia — na docelowych urządzeniach lokalu.

Jeśli Stripe jest wyłączony, nie aktywuj polityk wymagających zadatku. Brak providera
nie może prowadzić do cichego przyjęcia płatnej rezerwacji bez płatności.

## 1. Kopia, próba migracji i wdrożenie

1. Wykonaj kopię PostgreSQL i potwierdź, że da się ją odtworzyć.
2. Odtwórz kopię wraz z konfiguracją lokalu w odizolowanej instancji próbnej.
3. Na odtworzonej kopii uruchom migracje do bieżącego `head`.
4. Potwierdź `0068_reservation_closure`, raport gotowości oraz test akceptacyjny z sekcji 4.
5. Dopiero po zielonej próbie wykonaj nową kopię produkcyjną i zatrzymaj zapisy na czas właściwej migracji.
6. Wdróż ten sam, zweryfikowany obraz aplikacji i uruchom migrację produkcyjną do `head`.
7. Nie uruchamiaj aplikacji na schemacie starszym niż wdrożony kod.

Przykład dla instancji próbnej, a następnie produkcyjnej:

```powershell
docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

## 2. Konfiguracja lokalu

Przed opublikowaniem widgetu ustaw:

- godziny serwisów i ostatnie zasiadki,
- czasy wizyt dla wszystkich wielkości grup,
- sale, stoły, pojemności i sąsiedztwo,
- dozwolone konfiguracje łączenia stołów,
- limity osób i rezerwacji oraz wyjątki kalendarza,
- kolejność zapełniania sal,
- kontakt i adres administratora danych,
- zasady auto-potwierdzenia oraz przypomnień.

Widget pozostaje domyślnie wyłączony po onboardingu. Włącz go dopiero po zapisaniu
pełnej konfiguracji v2. Backend działa fail-closed: brak v2 nie uruchamia starego
formularza.

## 3. Konta i minimalny dostęp

- Administrator: pełna konfiguracja i operacje.
- Manager: tylko jawnie przyznane obszary, w tym osobno analityka, reguły, CRM
  oraz eksport.
- Recepcja / Host: operacje, host, dane kontaktowe i przekroczenie limitu po
  ostrzeżeniu; bez finansów, danych wrażliwych, eksportu oraz zarządzania CRM.
- Pracownik / kuchnia: wyłącznie bezpieczna lista własnego dnia.

Przetestuj cofnięcie każdego uprawnienia na już zalogowanej sesji.

## 4. Test akceptacyjny

Na kopii konfiguracji produkcyjnej wykonaj co najmniej:

1. rezerwację 2-osobową na pojedynczy stół,
2. rezerwację dużej grupy na różne konfiguracje, np. `4+2` i `6+4`,
3. konflikt równoległych prób na ten sam zasób,
4. wpis na waitlistę, ofertę, akceptację i wygaśnięcie,
5. przekroczenie limitu przez Recepcję po ostrzeżeniu i z podanym powodem,
6. zmianę stołu w widoku hosta oraz zakończenie wizyty,
7. publiczną rezerwację oraz jednorazowe wejście z linku zarządzania, po którym zmiana i anulowanie
   korzystają z szyfrowanej sesji w cookie `HttpOnly` — bez kopiowania surowego tokenu do storage lub URL,
8. grant i wycofanie zgody, eksport CRM, scalenie oraz cofnięcie scalenia,
9. rekomendację z symulacją, przyjęciem i odrzuceniem,
10. brak dostępu do PII po odebraniu odpowiedniego prawa.

## 5. Obserwacja po starcie

Przez pierwszą zmianę sprawdzaj:

- endpoint administratora `/api/ops/rezerwacje/health`,
- liczbę i wiek oczekujących wiadomości,
- wpisy `failed`, `uncertain` i wygasłe holdy,
- błędy 409 jako prawidłowe konflikty biznesowe, a 5xx jako alarm,
- czas odpowiedzi dostępności i tworzenia rezerwacji,
- zgodność liczby wizyt na osi hosta z bazą rezerwacji.

Raport gotowości nie zawiera nazwisk, kontaktów, notatek ani treści wiadomości.

### Kryterium go/no-go

- `SCHEMA_0068` musi mieć stan `ok`, a `PUBLIC_WIDGET_V2` dodatkowo raportować
  `v2=true` i `privacy_ready=true` przed opublikowaniem widgetu.
- Stan globalny `blocked` zatrzymuje rollout.
- Każdy stan `attention` musi mieć przypisaną osobę, przyczynę i świadomą decyzję. Nie wolno
  akceptować `attention` dla funkcji, którą lokal właśnie aktywuje.
- Brak providera komunikacji jest dopuszczalny tylko przy wyłączonych zależnych przypomnieniach
  lub kanałach; brak Stripe wyłącznie przy wyłączonych politykach płatności.
- Po właściwej migracji powtórz test akceptacyjny i dopiero wtedy uruchom zapisy publiczne.

## 6. Bezpieczny rollback

1. Wyłącz `rezerwacje_online`, aby zatrzymać nowe zapisy publiczne.
2. Pozostaw ręczną obsługę lokalu i nie przełączaj odczytu na Google.
3. Zabezpiecz bazę oraz logi techniczne bez PII.
4. Jeśli migracja ma zostać cofnięta, najpierw potwierdź, że nowe tabele są puste.
   Migracja celowo odmawia destrukcyjnego downgrade przy istniejących danych.
5. Napraw kod lub dane kanoniczne, uruchom test akceptacyjny i dopiero wtedy
   ponownie opublikuj widget.

Rollback aplikacji nie może usuwać rezerwacji, historii zgód, decyzji rekomendacji
ani zapisów audytowych.
