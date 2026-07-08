# Regulamin świadczenia usługi Lokalo

> **⚠️ SZABLON — WYMAGA WERYFIKACJI PRAWNEJ. To nie jest porada prawna.**
> Uzupełnij `[PLACEHOLDERY]`, sprawdź zgodność z realnym cennikiem/trialem (`backend/cennik.py`) i przekaż
> radcy prawnemu. Wersja: `[NR WERSJI]` · Obowiązuje od: `[DATA]`

## §1. Definicje

- **Operator** — `[NAZWA OPERATORA]`, `[ADRES]`, NIP `[NIP]`, świadczący usługę Lokalo.
- **Usługa / Lokalo** — aplikacja SaaS do zarządzania lokalem gastronomicznym (grafik pracy, rozliczenia,
  rezerwacje, POS, imprezy, powiadomienia) dostępna pod `[URL]`.
- **Klient / Najemca** — przedsiębiorca (właściciel lokalu) zawierający umowę o korzystanie z Usługi.
- **Użytkownik** — osoba korzystająca z konta w ramach lokalu Klienta (właściciel, pracownik).
- **Instancja** — wydzielone środowisko (aplikacja + baza) przypisane do jednego lokalu Klienta.

## §2. Charakter usługi i zawarcie umowy

1. Usługa świadczona jest w modelu SaaS (oprogramowanie jako usługa) i skierowana do **przedsiębiorców**
   (nie do konsumentów) — `[potwierdź to założenie; jeśli B2C, potrzebne są dodatkowe zapisy konsumenckie]`.
2. Umowa zostaje zawarta z chwilą rejestracji lokalu i akceptacji niniejszego Regulaminu oraz Polityki
   prywatności i Umowy powierzenia przetwarzania danych.
3. Do korzystania z Usługi niezbędne jest: `[WYMAGANIA TECHNICZNE — przeglądarka, łącze; ew. aplikacja mobilna]`.

## §3. Konto, plany i płatności

1. Usługa oferowana jest w planach `[Darmowy / Basic / Pro / Premium / Enterprise — spójnie z cennik.py]`
   o zakresie funkcji i limitach określonych w cenniku pod `[URL CENNIKA]`.
2. `[OPIS OKRESU PRÓBNEGO — np. 14 dni; wymaga podania karty; po okresie próbnym następuje automatyczne
   pobranie opłaty za wybrany plan, chyba że Klient zrezygnuje wcześniej — spójnie z rzeczywistą logiką.]`
3. Opłaty pobierane są `[cyklicznie / z góry]`. Dane karty są obsługiwane przez `[OPERATORA PŁATNOŚCI]`;
   Operator nie przechowuje pełnego numeru karty.
4. Faktury wystawiane są zgodnie z przepisami, w tym `[KSeF — jeśli dotyczy]`.
5. `[ZASADY ZMIANY PLANU, PRORACJI, ZALEGŁOŚCI — po okresie zaległości dostęp może zostać ograniczony do
   trybu tylko-do-odczytu; opisz mechanizm grace period spójnie z aplikacją.]`

## §4. Zasady korzystania

1. Klient odpowiada za dane wprowadzane do Usługi (w tym dane gości i pracowników) oraz za posiadanie
   podstaw prawnych do ich przetwarzania.
2. Zabronione jest: `[działania naruszające prawo, próby obejścia zabezpieczeń, nadmierne obciążanie
   infrastruktury, udostępnianie konta osobom nieuprawnionym itd.]`
3. Klient zapewnia poufność danych logowania Użytkowników.

## §5. Dostępność, wsparcie i SLA

1. Operator dokłada starań, by Usługa działała nieprzerwanie, z zastrzeżeniem przerw technicznych.
2. `[POZIOM WSPARCIA I SLA — czas reakcji, dostępność, okna serwisowe; jeśli brak SLA, zaznacz to wprost.]`
3. `[KOPIE ZAPASOWE — częstotliwość, sposób odtwarzania.]`

## §6. Odpowiedzialność

1. `[OGRANICZENIA ODPOWIEDZIALNOŚCI — w granicach dopuszczalnych prawem; w relacji B2B można ograniczyć,
   ale wymaga to precyzji prawnika. NIE kopiuj bezrefleksyjnie.]`
2. Operator nie odpowiada za treść i legalność danych wprowadzonych przez Klienta.

## §7. Rozwiązanie umowy i eksport danych

1. Klient może rozwiązać umowę `[TRYB I OKRES WYPOWIEDZENIA]`.
2. Po rozwiązaniu Klient ma prawo do eksportu swoich danych w terminie `[X DNI]`, po którym dane zostają
   usunięte/zanonimizowane zgodnie z Polityką prywatności i Umową powierzenia.

## §8. Zmiany Regulaminu

O zmianach Operator informuje z wyprzedzeniem `[SPOSÓB I TERMIN]`. Dalsze korzystanie z Usługi po wejściu
zmian w życie oznacza ich akceptację, chyba że Klient rozwiąże umowę.

## §9. Prawo właściwe i spory

Prawem właściwym jest prawo polskie. Spory rozstrzyga `[SĄD WŁAŚCIWY DLA SIEDZIBY OPERATORA / inny — do ustalenia]`.

## §10. Postanowienia końcowe

Integralną częścią umowy są: Polityka prywatności oraz Umowa powierzenia przetwarzania danych osobowych.
Wersja Regulaminu: `[NR]`, data: `[DATA]`.
