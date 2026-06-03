import { ddmmyyyy } from './format'

// Generuje listę tygodni roboczych (środa -> wtorek), od -2 do +5 względem
// bieżącego tygodnia. Zwraca opcje { value: "YYYY-MM-DD|YYYY-MM-DD", label }
// oraz wartość domyślną (bieżący tydzień). Logika 1:1 z poprzednią aplikacją.
export function generujOpcjeTygodni() {
  const opcje = []
  const dzis = new Date()
  const startSroda = new Date(dzis)
  let przesuniecie = dzis.getDay() - 3 // 3 = środa
  if (przesuniecie < 0) przesuniecie += 7
  startSroda.setDate(dzis.getDate() - przesuniecie)

  let domyslny = ''
  for (let i = -2; i <= 5; i++) {
    const sroda = new Date(startSroda)
    sroda.setDate(startSroda.getDate() + i * 7)
    const wtorek = new Date(sroda)
    wtorek.setDate(sroda.getDate() + 6)

    const sStr = sroda.toISOString().slice(0, 10)
    const wStr = wtorek.toISOString().slice(0, 10)
    const value = `${sStr}|${wStr}`
    if (i === 0) domyslny = value
    opcje.push({ value, label: `${ddmmyyyy(sStr)} — ${ddmmyyyy(wStr)}` })
  }
  return { opcje, domyslny }
}
