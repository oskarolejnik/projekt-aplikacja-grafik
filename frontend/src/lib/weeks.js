import { ddmmyyyy } from './format'

// Czytelne etykiety dla tygodni najbliższych bieżącemu (reszta = sam zakres dat).
const TAGI = { '-1': 'Poprzedni tydzień', 0: 'Bieżący tydzień', 1: 'Przyszły tydzień' }

// Generuje listę tygodni roboczych (środa -> wtorek), od -2 do +5 względem bieżącego.
// Zwraca opcje { value: "YYYY-MM-DD|YYYY-MM-DD", label } oraz wartości pomocnicze:
//   domyslny/biezacy (i=0) i przyszly (i=1) — do domyślnego ustawiania widoków.
export function generujOpcjeTygodni() {
  const opcje = []
  const dzis = new Date()
  const startSroda = new Date(dzis)
  let przesuniecie = dzis.getDay() - 3 // 3 = środa
  if (przesuniecie < 0) przesuniecie += 7
  startSroda.setDate(dzis.getDate() - przesuniecie)

  let biezacy = ''
  let przyszly = ''
  for (let i = -2; i <= 5; i++) {
    const sroda = new Date(startSroda)
    sroda.setDate(startSroda.getDate() + i * 7)
    const wtorek = new Date(sroda)
    wtorek.setDate(sroda.getDate() + 6)

    const sStr = sroda.toISOString().slice(0, 10)
    const wStr = wtorek.toISOString().slice(0, 10)
    const value = `${sStr}|${wStr}`
    if (i === 0) biezacy = value
    if (i === 1) przyszly = value

    const zakres = `${ddmmyyyy(sStr)} — ${ddmmyyyy(wStr)}`
    const tag = TAGI[i]
    opcje.push({ value, label: tag ? `${tag} · ${zakres}` : zakres })
  }
  return { opcje, domyslny: biezacy, biezacy, przyszly }
}
