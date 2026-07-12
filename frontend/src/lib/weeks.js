import { ddmmyyyy } from './format'

// Czytelne etykiety dla tygodni najbliższych bieżącemu (reszta = sam zakres dat).
const TAGI = { '-1': 'Poprzedni tydzień', 0: 'Bieżący tydzień', 1: 'Przyszły tydzień' }
const TAGI_MC = { '-1': 'Poprzedni miesiąc', 0: 'Bieżący miesiąc', 1: 'Przyszły miesiąc' }
const NAZWY_MC = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec',
  'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień']

// Generuje listę tygodni roboczych, od -2 do +5 względem bieżącego.
// `poczatekTygodnia` = dzień startu tygodnia grafiku z konfiguracji lokalu
// (0=poniedziałek … 6=niedziela; domyślnie 2=środa — historyczna konwencja).
// Zwraca opcje { value: "YYYY-MM-DD|YYYY-MM-DD", label } oraz wartości pomocnicze:
//   domyslny/biezacy (i=0) i przyszly (i=1) — do domyślnego ustawiania widoków.
export function generujOpcjeTygodni(poczatekTygodnia = 2) {
  const opcje = []
  const dzis = new Date()
  // Zakres jest datą kalendarzową lokalu, nie chwilą UTC. `toISOString()` cofał
  // lokalną północ o jeden dzień w Europe/Warsaw i przesuwał cały grafik.
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  // konwencja configu: 0=pon…6=nie → JS getDay(): 0=nie, 1=pon…6=sob
  const jsDzien = (Number.isInteger(poczatekTygodnia) ? ((poczatekTygodnia % 7) + 7) % 7 + 1 : 3) % 7
  const startTygodnia = new Date(dzis)
  let przesuniecie = dzis.getDay() - jsDzien
  if (przesuniecie < 0) przesuniecie += 7
  startTygodnia.setDate(dzis.getDate() - przesuniecie)

  let biezacy = ''
  let przyszly = ''
  for (let i = -2; i <= 5; i++) {
    const start = new Date(startTygodnia)
    start.setDate(startTygodnia.getDate() + i * 7)
    const koniec = new Date(start)
    koniec.setDate(start.getDate() + 6)

    const sStr = iso(start)
    const kStr = iso(koniec)
    const value = `${sStr}|${kStr}`
    if (i === 0) biezacy = value
    if (i === 1) przyszly = value

    const zakres = `${ddmmyyyy(sStr)} — ${ddmmyyyy(kStr)}`
    const tag = TAGI[i]
    opcje.push({ value, label: tag ? `${tag} · ${zakres}` : zakres })
  }
  return { opcje, domyslny: biezacy, biezacy, przyszly }
}

// Miesiące kalendarzowe (1. → ostatni dzień), od -2 do +5 względem bieżącego.
// Ten sam kształt zwrotki co generujOpcjeTygodni — WeekSelect/weekRange działają bez zmian.
export function generujOpcjeMiesiecy() {
  const opcje = []
  const dzis = new Date()
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  let biezacy = ''
  let przyszly = ''
  for (let i = -2; i <= 5; i++) {
    const pierwszy = new Date(dzis.getFullYear(), dzis.getMonth() + i, 1)
    const ostatni = new Date(dzis.getFullYear(), dzis.getMonth() + i + 1, 0)
    const value = `${iso(pierwszy)}|${iso(ostatni)}`
    if (i === 0) biezacy = value
    if (i === 1) przyszly = value
    const nazwa = `${NAZWY_MC[pierwszy.getMonth()]} ${pierwszy.getFullYear()}`
    const tag = TAGI_MC[i]
    opcje.push({ value, label: tag ? `${tag} · ${nazwa}` : nazwa })
  }
  return { opcje, domyslny: biezacy, biezacy, przyszly }
}

// Dyspozytor cyklu grafiku z konfiguracji lokalu: 'tydzien' (domyślnie) | 'miesiac'.
export function generujOpcjeCyklu(cykl = 'tydzien', poczatekTygodnia = 2) {
  return cykl === 'miesiac' ? generujOpcjeMiesiecy() : generujOpcjeTygodni(poczatekTygodnia)
}
