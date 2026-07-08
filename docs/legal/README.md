# Dokumenty prawne Lokalo — SZABLONY do weryfikacji prawnej

> ## ⚠️ TO SĄ SZABLONY, NIE GOTOWE DOKUMENTY
> Poniższe pliki to **rusztowanie przygotowane przez inżyniera, nie przez prawnika**. Odzwierciedlają
> rzeczywiste przepływy danych w aplikacji, ale **przed publikacją MUSZĄ zostać zweryfikowane przez
> radcę prawnego / kancelarię specjalizującą się w RODO**. Nie są poradą prawną.
>
> Wszystkie wartości do uzupełnienia oznaczono `[W NAWIASACH KWADRATOWYCH]`. Zanim cokolwiek opublikujesz:
> 1. wypełnij placeholdery (checklista niżej),
> 2. daj komplet do weryfikacji prawnikowi,
> 3. dopiero opublikowaną, zaakceptowaną wersję podłącz w aplikacji.

## Pliki

| Plik | Co to jest | Kto jest administratorem | Gdzie się pokazuje |
|---|---|---|---|
| [`polityka-prywatnosci.md`](polityka-prywatnosci.md) | Polityka prywatności serwisu Lokalo | **Lokalo** (operator) — dane KONTA właściciela lokalu (login, faktury, płatności) | strona `/polityka`, rejestracja, stopka |
| [`regulamin.md`](regulamin.md) | Regulamin świadczenia usługi (SaaS) | umowa Lokalo ↔ najemca (właściciel lokalu) | strona `/regulamin`, rejestracja |
| [`umowa-powierzenia-dpa.md`](umowa-powierzenia-dpa.md) | Umowa powierzenia przetwarzania (art. 28 RODO) | **najemca = administrator**, **Lokalo = podmiot przetwarzający** danych gości i pracowników | akceptacja przy rejestracji lokalu |
| [`klauzula-informacyjna-gosc.md`](klauzula-informacyjna-gosc.md) | Klauzula informacyjna + zgody dla gościa rezerwującego | **lokal (najemca)** — dane gościa; Lokalo tylko przetwarza | widget rezerwacji online |

## Dlaczego cztery dokumenty — role RODO w modelu multi-tenant

Lokalo to SaaS multi-tenant. Kluczowe rozróżnienie ról decyduje o wszystkim:

- **Dane konta właściciela lokalu** (e-mail logowania, dane do faktury, dane karty): administratorem jest
  **Lokalo** → obejmuje je *Polityka prywatności Lokalo*.
- **Dane gości i pracowników** wprowadzane do aplikacji przez lokal: administratorem jest **lokal (najemca)**,
  a **Lokalo jest jedynie podmiotem przetwarzającym** (art. 28 RODO) → to reguluje *Umowa powierzenia (DPA)*,
  a wobec gościa obowiązek informacyjny spełnia lokal (*Klauzula informacyjna dla gościa*).
- Relację handlową (co obejmuje usługa, płatności, odpowiedzialność, SLA) reguluje *Regulamin*.

## Jak to się ma do rzeczywistej architektury (fakty z kodu)

Szablony opisują to, co aplikacja **naprawdę robi** — zweryfikuj z zespołem/kodem przy uzupełnianiu:

- **Szyfrowanie danych wrażliwych at-rest**: telefon, e-mail i alergie gościa są szyfrowane (Fernet/AES-128 + HMAC,
  `backend/szyfrowanie.py`, `ENCRYPTION_KEY`). Hasła: bcrypt. PAN karty **nie jest przechowywany** (tylko token + ostatnie 4 cyfry).
- **Izolacja najemców**: instance-per-tenant (osobna instancja + baza na lokal).
- **Prawa podmiotu danych** zaimplementowane w `backend/routers/rodo.py`: eksport (art. 15/20), anonimizacja (art. 17),
  retencja (art. 5). Dostęp do danych wrażliwych logowany (`AuditLog`).
- **Szczególna kategoria danych (art. 9)**: alergie/dieta gościa — wymagają odrębnej podstawy (zgoda) i są szyfrowane.
- **Podprocesorzy** (do potwierdzenia, które są realnie podłączone): hosting/VPS, operator płatności (Stripe — obecnie
  tryb testowy), bramka e-mail (SMTP), bramka SMS, push (FCM), KSeF (faktury), opcjonalnie dostawca AI (skrzynka zapytań),
  Google Calendar (import). Pełną, aktualną listę utrzymuj w załączniku do DPA.

## Checklista placeholderów do uzupełnienia

- `[NAZWA OPERATORA / SPÓŁKA]`, `[FORMA PRAWNA]`, `[NIP]`, `[REGON]`, `[KRS jeśli dotyczy]`, `[ADRES SIEDZIBY]`
- `[E-MAIL KONTAKTOWY]`, `[E-MAIL DO SPRAW RODO / IOD]`, `[TELEFON]`
- `[CZY POWOŁANO IOD — TAK/NIE + dane]`
- `[NAZWA DOMENY / URL SERWISU]`
- `[LISTA PODPROCESORÓW + kraje + podstawy transferu poza EOG]`
- `[OKRESY RETENCJI per kategoria danych]`
- `[NAZWA/WERSJA I DATA WEJŚCIA W ŻYCIE każdego dokumentu]`
- `[WŁAŚCIWY SĄD / PRAWO WŁAŚCIWE]`
- `[CENNIK / OKRES TRIAL / ZASADY PŁATNOŚCI — spójne z cennik.py]`

## Uwaga o mechanice (osobny temat)

Ten katalog to **treść**. Samo *zbieranie i dowodzenie zgód* (checkbox akceptacji przy rejestracji, zgoda gościa
w widgecie rezerwacji, model `ZgodaAkceptacja` z wersją/datą/IP, strony `/polityka` i `/regulamin`) to warstwa
**mechaniki w aplikacji** — do zbudowania osobno, gdy dokumenty będą zaakceptowane przez prawnika.
