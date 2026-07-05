import { ddmmyyyy } from './format'

// Czytelne etykiety dla tygodni najbliższych bieżącemu (reszta = sam zakres dat).
const TAGI = { '-1': 'Poprzedni tydzień', 0: 'Bieżący tydzień', 1: 'Przyszły tydzień' }

// Generuje listę tygodni roboczych, od -2 do +5 względem bieżącego.
// `poczatekTygodnia` = dzień startu tygodnia grafiku z konfiguracji lokalu
// (0=poniedziałek … 6=niedziela; domyślnie 2=środa — historyczna konwencja).
// Zwraca opcje { value: "YYYY-MM-DD|YYYY-MM-DD", label } oraz wartości pomocnicze:
//   domyslny/biezacy (i=0) i przyszly (i=1) — do domyślnego ustawiania widoków.
export function generujOpcjeTygodni(poczatekTygodnia = 2) {
  const opcje = []
  const dzis = new Date()
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

    const sStr = start.toISOString().slice(0, 10)
    const kStr = koniec.toISOString().slice(0, 10)
    const value = `${sStr}|${kStr}`
    if (i === 0) biezacy = value
    if (i === 1) przyszly = value

    const zakres = `${ddmmyyyy(sStr)} — ${ddmmyyyy(kStr)}`
    const tag = TAGI[i]
    opcje.push({ value, label: tag ? `${tag} · ${zakres}` : zakres })
  }
  return { opcje, domyslny: biezacy, biezacy, przyszly }
}
