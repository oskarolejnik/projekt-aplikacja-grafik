# Umowa powierzenia przetwarzania danych osobowych (DPA)

> **⚠️ SZABLON — WYMAGA WERYFIKACJI PRAWNEJ. To nie jest porada prawna.**
> Zawierana pomiędzy Lokalo (podmiot przetwarzający) a lokalem (administrator) — akceptowana przy rejestracji.
> Uzupełnij `[PLACEHOLDERY]` i przekaż radcy prawnemu. Wersja: `[NR]` · Obowiązuje od: `[DATA]`

Umowa w wykonaniu **art. 28 RODO**, pomiędzy:
- **Administratorem** — `[Klient: dane lokalu — nazwa, NIP, adres]` (dalej „**Administrator**"), oraz
- **Podmiotem przetwarzającym** — `[NAZWA OPERATORA]`, NIP `[NIP]` (dalej „**Procesor**" / „**Lokalo**").

## §1. Przedmiot i cel

1. Administrator powierza Procesorowi przetwarzanie danych osobowych **wyłącznie w celu i zakresie
   niezbędnym do świadczenia Usługi Lokalo** (zarządzanie lokalem: grafik, rozliczenia, rezerwacje, POS, imprezy).
2. Procesor przetwarza dane wyłącznie na **udokumentowane polecenie** Administratora, którym jest korzystanie
   z Usługi zgodnie z Regulaminem oraz niniejszą Umową.

## §2. Charakter, kategorie osób i rodzaje danych

| Kategoria osób | Rodzaje danych | Uwaga |
|---|---|---|
| Goście lokalu | imię/nazwisko, telefon, e-mail, historia rezerwacji, liczba osób, notatki, oznaczenia (VIP/tagi) | telefon, e-mail i alergie **szyfrowane** |
| Goście — dane szczególne | **alergie / dieta** (art. 9 RODO — dane o zdrowiu) | wymaga podstawy szczególnej (zgoda gościa) |
| Pracownicy | imię/nazwisko, stanowisko, kwalifikacje, dyspozycyjność, grafik, dane rozliczeniowe/płacowe, ew. badania | dostęp do płac objęty audytem |
| Kontakty imprezowe / klienci eventów | dane kontaktowe, ustalenia, zadatki | — |

Czas trwania przetwarzania: przez okres obowiązywania umowy o świadczenie Usługi.
`[Zweryfikuj zakres z rzeczywistym modelem danych: Termin, Pracownik, ProfilGoscia, rozliczenia.]`

## §3. Obowiązki Procesora

Procesor zobowiązuje się w szczególności do:
1. przetwarzania danych wyłącznie na polecenie Administratora;
2. zapewnienia, by osoby upoważnione do przetwarzania zobowiązały się do zachowania poufności;
3. wdrożenia środków bezpieczeństwa odpowiednich do ryzyka (art. 32 RODO) — **załącznik nr 1**;
4. przestrzegania warunków korzystania z **podprocesorów** (§4);
5. pomocy Administratorowi w realizacji **praw osób, których dane dotyczą** (dostęp, sprostowanie, usunięcie,
   przenoszenie) — w aplikacji dostępne są funkcje eksportu, anonimizacji i retencji danych;
6. pomocy w wywiązaniu się z obowiązków z art. 32–36 RODO (bezpieczeństwo, zgłaszanie naruszeń, DPIA);
7. **zgłaszania naruszeń** ochrony danych bez zbędnej zwłoki, nie później niż `[np. 24/48 h]` od stwierdzenia;
8. po zakończeniu świadczenia — **usunięcia lub zwrotu** danych, wedle wyboru Administratora, oraz usunięcia kopii,
   z wyjątkiem przechowywania wymaganego prawem.

## §4. Podprocesorzy

1. Administrator wyraża **ogólną zgodę** na korzystanie z podprocesorów niezbędnych do świadczenia Usługi.
   Aktualna lista: **załącznik nr 2** (`[HOSTING, OPERATOR PŁATNOŚCI, E-MAIL, SMS, PUSH, KSeF, opcjonalnie AI/Google]`).
2. Procesor informuje o zamierzonych zmianach podprocesorów z wyprzedzeniem `[X DNI]`, umożliwiając sprzeciw.
3. Procesor nakłada na podprocesorów obowiązki analogiczne do niniejszej Umowy.
4. `[Transfery poza EOG — jeśli występują — na podstawie standardowych klauzul umownych (SCC) lub decyzji adekwatności.]`

## §5. Bezpieczeństwo — załącznik nr 1 (środki techniczne i organizacyjne)

Procesor stosuje m.in.: **szyfrowanie danych wrażliwych w spoczynku** (AES/Fernet) i w transmisji (TLS),
**hasła jako skróty bcrypt**, kontrolę dostępu opartą na rolach, **dziennik audytu** dostępu do danych wrażliwych,
**izolację danych między administratorami** (instance-per-tenant), ograniczenie prób logowania, nagłówki
bezpieczeństwa, kopie zapasowe `[opis]`. `[Zweryfikuj i doprecyzuj — powyższe odzwierciedla stan aplikacji.]`

## §6. Audyt

Administrator ma prawo do weryfikacji zgodności Procesora `[TRYB — np. na podstawie kwestionariusza / raportu /
audytu za wyprzedzeniem, w godzinach pracy, z zachowaniem poufności]`.

## §7. Odpowiedzialność i postanowienia końcowe

`[Zasady odpowiedzialności, prawo właściwe (polskie), rozstrzyganie sporów, pierwszeństwo dokumentów.]`
W sprawach nieuregulowanych stosuje się RODO i przepisy krajowe. Wersja: `[NR]`, data: `[DATA]`.

---
**Załącznik nr 1** — Środki bezpieczeństwa (§5). **Załącznik nr 2** — Lista podprocesorów.
`[Utrzymuj załącznik nr 2 jako aktualną, wersjonowaną listę — powinien odzwierciedlać realnie podłączone usługi.]`
