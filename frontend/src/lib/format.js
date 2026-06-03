// Drobne pomocniki formatowania dat/godzin (zgodne z poprzednią aplikacją).

// 2026-06-01 -> 01.06.2026
export const ddmmyyyy = (iso) => (iso || '').split('-').reverse().join('.')

// "08:00:00" -> "08:00"
export const hhmm = (t) => (t ? String(t).slice(0, 5) : '')

// Indeks getDay() -> polska nazwa dnia
export const NAZWY_DNI = [
  'Niedziela',
  'Poniedziałek',
  'Wtorek',
  'Środa',
  'Czwartek',
  'Piątek',
  'Sobota',
]

// Lista kolejnych dni (YYYY-MM-DD) od start do end włącznie
export function zakresDni(startISO, endISO) {
  const dni = []
  const cur = new Date(startISO)
  const end = new Date(endISO)
  while (cur <= end) {
    dni.push(cur.toISOString().slice(0, 10))
    cur.setDate(cur.getDate() + 1)
  }
  return dni
}
