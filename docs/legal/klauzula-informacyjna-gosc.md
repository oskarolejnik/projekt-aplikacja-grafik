# Klauzula informacyjna i zgody dla gościa (rezerwacja online)

> **⚠️ SZABLON — WYMAGA WERYFIKACJI PRAWNEJ. To nie jest porada prawna.**
> Administratorem danych gościa jest **LOKAL** (najemca), nie Lokalo. Ta klauzula spełnia obowiązek
> informacyjny lokalu wobec gościa (art. 13 RODO) i definiuje zgody zbierane w widgecie rezerwacji.
> Uzupełnij `[PLACEHOLDERY]`. Docelowo tekst administratora (lokalu) powinien być konfigurowalny per lokal.

## A. Klauzula informacyjna (art. 13 RODO) — do wyświetlenia przy formularzu rezerwacji

Administratorem Twoich danych jest **`[NAZWA LOKALU]`**, `[ADRES]`, kontakt: `[E-MAIL/TELEFON LOKALU]`.
Twoje dane (imię/nazwisko, telefon, e-mail, liczba osób, ewentualne uwagi) przetwarzamy w celu:

- **obsługi rezerwacji** — podstawa: art. 6 ust. 1 lit. b RODO (podjęcie działań na Twoje żądanie / umowa);
- **kontaktu w sprawie rezerwacji** (potwierdzenie, przypomnienie, zmiana) — podstawa: jw. / uzasadniony interes;
- `[opcjonalnie: dochodzenie/obrona roszczeń — art. 6 ust. 1 lit. f.]`

Dane przechowujemy przez `[OKRES — np. czas niezbędny do obsługi rezerwacji i przedawnienia roszczeń]`.
Odbiorcami danych mogą być dostawcy IT działający na nasze zlecenie (m.in. dostawca oprogramowania do zarządzania
rezerwacjami — **Lokalo**, oraz bramki e-mail/SMS). Masz prawo dostępu do danych, ich sprostowania, usunięcia,
ograniczenia, przenoszenia, sprzeciwu oraz wniesienia skargi do **PUODO**. Podanie danych kontaktowych jest
dobrowolne, ale niezbędne do dokonania rezerwacji.

## B. Zgody zbierane w formularzu

> Zasada RODO: **zgody muszą być odrębne, dobrowolne i niepołączone** (nie jeden zbiorczy checkbox). Zgoda
> marketingowa **nie może** być warunkiem dokonania rezerwacji.

1. **[WYMAGANE do rezerwacji]** — potwierdzenie zapoznania się z informacją o przetwarzaniu danych:
   > „Zapoznałem/am się z informacją o przetwarzaniu moich danych w celu obsługi rezerwacji przez `[NAZWA LOKALU]`."
   *(To nie jest zgoda marketingowa — to potwierdzenie obowiązku informacyjnego; bez niego nie wysyłamy formularza.)*

2. **[OPCJONALNE — osobny opt-in] Alergie / dieta (dane szczególne, art. 9 RODO)** — pole wypełniane
   dobrowolnie; jeśli gość je poda, wymagana odrębna zgoda:
   > „Wyrażam zgodę na przetwarzanie podanych przeze mnie informacji o alergiach/diecie w celu dostosowania
   > obsługi. Wiem, że mogę ją wycofać."
   *(W aplikacji alergie są szyfrowane; pole pozostaw puste, jeśli gość nie chce ich podawać.)*

3. **[OPCJONALNE — osobny opt-in] Marketing:**
   > „Wyrażam zgodę na otrzymywanie informacji handlowych od `[NAZWA LOKALU]` drogą `[e-mail/SMS]`.
   > Zgodę mogę wycofać w każdej chwili."
   *(Nie może być domyślnie zaznaczona ani wymagana do rezerwacji. Dowód zapisuje
   `RezerwacjaZgodaPubliczna`; ewentualna synchronizacja preferencji CRM jest osobną polityką.)*

## C. Stan mechaniki w aplikacji

Aby zgoda była **dowodliwa** (RODO wymaga wykazania zgody), przy zapisie należy utrwalić: **treść/wersję**
zgody, **datę** i (dla zgód online) **adres IP/znacznik**. Widget R5a realizuje ten kontrakt przez
`RezerwacjaZgodaPubliczna`: zapisuje wersje i daty potwierdzenia informacji, marketingu i danych
szczególnych oraz pseudonimizowany HMAC adresu IP — nigdy surowy adres IP w rekordzie zgody.

Mechanika jest rozdzielona zgodnie z celem przetwarzania:

- potwierdzenie informacji (pkt B.1) jest wymagane do wysłania formularza;
- marketing (pkt B.3) jest osobnym, domyślnie wyłączonym opt-inem i jego odmowa nie blokuje rezerwacji;
- pole alergii/diety/potrzeb dostępności wymaga osobnej zgody (pkt B.2), a treść jest szyfrowana at-rest;
- okres po realizacji wizyty jest konfigurowany per lokal; deadline zapisuje się przy zebraniu
  informacji i późniejsza zmiana konfiguracji nie może go retroaktywnie wydłużyć;
- audytowana retencja działa automatycznie w tle i usuwa także wygasłe zaszyfrowane odpowiedzi
  idempotencyjne, tokeny oraz techniczne rekordy publicznego przepływu;
- eksport i usunięcie danych są dostępne w torze administracyjnym i samoobsługowym gościa.

Treści, podstawy prawne, okresy oraz dane administratora nadal wymagają uzupełnienia przez lokal i
akceptacji prawnika przed komercyjną publikacją. Mechanizm wersjonuje tekst zwrócony przez konfigurację
widgetu; zmiana zaakceptowanej treści powinna otrzymać nową wersję.

## D. Rola Lokalo

Lokalo (dostawca oprogramowania) jest wobec tych danych **podmiotem przetwarzającym** działającym na zlecenie
lokalu — na podstawie *Umowy powierzenia (DPA)*. To lokal, jako administrator, odpowiada za treść tej klauzuli
i zebranie zgód; Lokalo dostarcza mechanizm i zabezpieczenia (szyfrowanie, eksport, usuwanie danych).
