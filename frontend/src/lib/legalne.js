// Treść dokumentów prawnych pokazywana na stronie (WERSJA ROBOCZA — do finalizacji przez prawnika).
// Pełne szablony: docs/legal/*.md. Po akceptacji prawnej podmień treść tutaj — jedno miejsce.
// WERSJA musi być spójna z backendem (flota.ZGODA_WERSJA), bo tę wersję zapisujemy przy akceptacji.
export const WERSJA = '1.0'
export const AKTUALIZACJA = '2026-07-08'
export const KONTAKT_RODO = 'kontakt@grafikpracy.pl'   // [PODMIEŃ na docelowy adres kontaktowy]

// [W NAWIASACH] — dane operatora do uzupełnienia przed publikacją finalnej wersji.
export const POLITYKA = {
  tytul: 'Polityka prywatności',
  wstep: 'Opisuje, jak przetwarzamy dane osobowe użytkowników serwisu Lokalo (właścicieli i pracowników lokali). Dane gości i pracowników wprowadzane do aplikacji przez lokal przetwarzamy w imieniu lokalu — reguluje to odrębna umowa powierzenia.',
  sekcje: [
    { h: '1. Administrator', t: 'Administratorem danych użytkowników serwisu jest [NAZWA OPERATORA], [ADRES], NIP [NIP]. Kontakt w sprawach danych osobowych: ' + KONTAKT_RODO + '.' },
    { h: '2. Jakie dane i w jakim celu', t: 'Przetwarzamy dane konta (e-mail logowania, hasło przechowywane jako skrót bcrypt, nazwa lokalu), dane rozliczeniowe (NIP i dane do faktury, token karty i ostatnie 4 cyfry — pełnego numeru karty NIE przechowujemy) oraz dane techniczne (adres IP, logi, dziennik audytu). Cele: prowadzenie konta i uwierzytelnianie, obsługa płatności i faktur, bezpieczeństwo. Podstawy: wykonanie umowy (art. 6 ust. 1 lit. b), obowiązek prawny (lit. c) oraz uzasadniony interes — bezpieczeństwo (lit. f).' },
    { h: '3. Jak długo', t: 'Dane konta i rozliczeniowe przechowujemy przez okres umowy oraz po niej przez czas wymagany przepisami (m.in. dokumentacja księgowa) lub do przedawnienia roszczeń. Logi bezpieczeństwa — przez okres niezbędny do ich celu.' },
    { h: '4. Bezpieczeństwo', t: 'Stosujemy m.in.: szyfrowanie danych wrażliwych w spoczynku i transmisji (TLS), hasła wyłącznie jako skróty, kontrolę dostępu opartą na rolach, dziennik audytu dostępu do danych wrażliwych oraz izolację danych między lokalami.' },
    { h: '5. Odbiorcy', t: 'Dane mogą być powierzane zaufanym dostawcom działającym na nasze zlecenie (hosting, operator płatności, bramki e-mail/SMS, powiadomienia). Aktualną listę udostępniamy na żądanie.' },
    { h: '6. Twoje prawa', t: 'Masz prawo dostępu do danych, sprostowania, usunięcia, ograniczenia, przenoszenia i sprzeciwu, a także cofnięcia zgody i wniesienia skargi do Prezesa Urzędu Ochrony Danych Osobowych (PUODO). Aby skorzystać z praw — napisz na ' + KONTAKT_RODO + '.' },
    { h: '7. Pliki cookie / pamięć lokalna', t: 'Wykorzystujemy pamięć przeglądarki w zakresie niezbędnym do działania serwisu (np. token sesji logowania). Nie stosujemy plików cookie do śledzenia. [Jeśli dodacie analitykę/marketing — opiszcie je i dodajcie zgodę.]' },
  ],
}

export const REGULAMIN = {
  tytul: 'Regulamin',
  wstep: 'Warunki korzystania z usługi Lokalo (oprogramowanie jako usługa dla lokali gastronomicznych).',
  sekcje: [
    { h: '1. Definicje', t: 'Operator — [NAZWA OPERATORA], dostawca usługi Lokalo. Klient — przedsiębiorca (właściciel lokalu) korzystający z usługi. Usługa — aplikacja do zarządzania lokalem (grafik, rozliczenia, rezerwacje, POS, imprezy).' },
    { h: '2. Zawarcie umowy', t: 'Usługa kierowana jest do przedsiębiorców. Umowa zostaje zawarta z chwilą rejestracji lokalu i akceptacji Regulaminu, Polityki prywatności oraz Umowy powierzenia przetwarzania danych.' },
    { h: '3. Plany i płatności', t: 'Usługa oferowana jest w planach (darmowy, basic, pro, premium) zgodnie z cennikiem. Plany płatne rozpoczynają się 14-dniowym okresem próbnym wymagającym podania karty; po jego zakończeniu następuje automatyczne pobranie opłaty, o ile Klient nie zrezygnuje wcześniej. Pełnego numeru karty nie przechowujemy.' },
    { h: '4. Zasady korzystania', t: 'Klient odpowiada za dane wprowadzane do usługi (w tym dane gości i pracowników) oraz za podstawy prawne ich przetwarzania. Zabronione są działania naruszające prawo, obchodzenie zabezpieczeń i udostępnianie konta osobom nieuprawnionym.' },
    { h: '5. Dostępność i dane', t: 'Dokładamy starań, aby usługa działała nieprzerwanie, z zastrzeżeniem przerw technicznych. Po rozwiązaniu umowy Klient ma prawo do eksportu swoich danych, po czym dane są usuwane lub anonimizowane zgodnie z Polityką prywatności.' },
    { h: '6. Zmiany i prawo właściwe', t: 'O zmianach Regulaminu informujemy z wyprzedzeniem. Prawem właściwym jest prawo polskie. Integralną częścią umowy są Polityka prywatności i Umowa powierzenia przetwarzania danych.' },
  ],
}

export const DOKUMENTY = { polityka: POLITYKA, regulamin: REGULAMIN }
