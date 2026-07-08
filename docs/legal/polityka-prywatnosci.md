# Polityka prywatności serwisu Lokalo

> **⚠️ SZABLON — WYMAGA WERYFIKACJI PRAWNEJ. To nie jest porada prawna.**
> Uzupełnij `[PLACEHOLDERY]` i przekaż do akceptacji radcy prawnemu przed publikacją.
> Wersja: `[NR WERSJI]` · Obowiązuje od: `[DATA]`

Niniejsza Polityka prywatności opisuje, jak **`[NAZWA OPERATORA]`** (dalej „**Operator**" lub „**Lokalo**")
przetwarza dane osobowe **użytkowników serwisu Lokalo** — tj. właścicieli i pracowników lokali gastronomicznych,
którzy zakładają konto i korzystają z aplikacji pod adresem `[URL SERWISU]`.

> **Zakres:** ta polityka dotyczy danych, których **administratorem jest Lokalo** — przede wszystkim danych
> KONTA i ROZLICZEŃ osoby zakładającej lokal. Dane gości i pracowników wprowadzane do aplikacji przez lokal
> przetwarzamy **w imieniu lokalu** jako podmiot przetwarzający — reguluje to odrębna *Umowa powierzenia (DPA)*,
> a obowiązek informacyjny wobec gościa spełnia lokal (zob. *Klauzula informacyjna dla gościa*).

## 1. Administrator danych

Administratorem danych osobowych jest **`[NAZWA OPERATORA / FORMA PRAWNA]`**, `[ADRES SIEDZIBY]`,
NIP `[NIP]`, REGON `[REGON]`, `[KRS jeśli dotyczy]`.
Kontakt w sprawach danych osobowych: **`[E-MAIL DO SPRAW RODO]`**, `[TELEFON]`.
`[Jeśli powołano Inspektora Ochrony Danych: dane kontaktowe IOD. Jeśli nie — usuń to zdanie.]`

## 2. Jakie dane przetwarzamy i w jakim celu

| Kategoria danych | Przykłady | Cel | Podstawa prawna (RODO) |
|---|---|---|---|
| Dane konta | e-mail (login), hasło (przechowywane jako skrót bcrypt), nazwa lokalu, typ lokalu | założenie i utrzymanie konta, uwierzytelnianie | art. 6 ust. 1 lit. b (umowa) |
| Dane rozliczeniowe | NIP, nazwa i adres do faktury, wybrany plan, historia subskrypcji | realizacja płatności, wystawianie faktur, KSeF | art. 6 ust. 1 lit. b i c (umowa, obowiązek prawny) |
| Dane płatnicze | **token karty i ostatnie 4 cyfry** (pełny numer karty / PAN **nie jest przechowywany**) | pobranie opłaty za subskrypcję po okresie próbnym | art. 6 ust. 1 lit. b |
| Dane techniczne / logi | adres IP, znaczniki czasu, zdarzenia bezpieczeństwa, dziennik audytu dostępu do danych wrażliwych | bezpieczeństwo, wykrywanie nadużyć, rozliczalność | art. 6 ust. 1 lit. f (uzasadniony interes) |
| Powiadomienia | adres e-mail / token push (jeśli włączone) | wysyłka powiadomień o działaniu usługi | art. 6 ust. 1 lit. b / f |

`[Zweryfikuj i uzupełnij zgodnie z rzeczywistym zakresem — powyższe wynika z modelu danych aplikacji: User, Subskrypcja, RejestracjaLokalu, AuditLog.]`

## 3. Okres przechowywania

Dane konta i rozliczeniowe przechowujemy przez okres obowiązywania umowy oraz po jej zakończeniu przez czas
wymagany przepisami (m.in. `[5 lat — dokumentacja księgowa/podatkowa]`) lub do przedawnienia roszczeń.
Logi bezpieczeństwa: `[OKRES]`. Szczegółowe okresy retencji: `[TABELA RETENCJI]`.

## 4. Odbiorcy danych i podprocesorzy

Dane mogą być powierzane zaufanym dostawcom działającym na nasze zlecenie (podmioty przetwarzające), w tym:
`[HOSTING/VPS]`, `[OPERATOR PŁATNOŚCI]`, `[BRAMKA E-MAIL]`, `[BRAMKA SMS]`, `[DOSTAWCA PUSH/FCM]`,
`[KSeF — podmiot publiczny]`, `[opcjonalnie: dostawca AI, Google]`.
Aktualną listę podprocesorów utrzymujemy w `[MIEJSCE — np. załącznik / podstrona]`.
`[Wskaż, czy występuje transfer poza EOG i na jakiej podstawie — SCC / decyzja adekwatności.]`

## 5. Bezpieczeństwo

Stosujemy środki techniczne i organizacyjne adekwatne do ryzyka, m.in.: **szyfrowanie danych wrażliwych
w spoczynku** (AES/Fernet), szyfrowanie transmisji (TLS), **hasła przechowywane wyłącznie jako skróty (bcrypt)**,
kontrolę dostępu opartą na rolach, **dziennik audytu** dostępu do danych wrażliwych, **izolację danych między
lokalami** (osobne instancje), nagłówki bezpieczeństwa oraz ograniczenie liczby prób logowania.
`[Zweryfikuj listę środków z zespołem — powyższe odzwierciedla stan kodu.]`

## 6. Prawa osoby, której dane dotyczą

Przysługuje Ci prawo do: dostępu do danych, sprostowania, usunięcia („prawo do bycia zapomnianym"),
ograniczenia przetwarzania, przenoszenia danych, sprzeciwu oraz cofnięcia zgody (bez wpływu na zgodność
z prawem przetwarzania przed cofnięciem). Masz też prawo wniesienia skargi do **Prezesa Urzędu Ochrony
Danych Osobowych (PUODO)**. Aby skorzystać z praw, napisz na `[E-MAIL DO SPRAW RODO]`.
W aplikacji dostępne są funkcje eksportu i usunięcia/anonimizacji danych.

## 7. Zgody i marketing

Wysyłka informacji marketingowych odbywa się wyłącznie za odrębną, dobrowolną zgodą (art. 6 ust. 1 lit. a RODO
oraz przepisy o komunikacji elektronicznej). Zgodę można w każdej chwili wycofać. `[Uzupełnij, jeśli prowadzicie marketing.]`

## 8. Pliki cookie / pamięć lokalna

Serwis wykorzystuje pamięć przeglądarki (localStorage/sessionStorage) w zakresie **niezbędnym do działania**
(np. token sesji logowania). `[Jeśli używacie cookies analitycznych/marketingowych — opisz je i dodaj baner zgody;
jeśli tylko techniczne — zaznacz, że zgoda nie jest wymagana.]`

## 9. Zmiany polityki

O istotnych zmianach poinformujemy z wyprzedzeniem `[SPOSÓB — e-mail / komunikat w aplikacji]`.
Data ostatniej aktualizacji: `[DATA]`.
