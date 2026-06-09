// Drobne pomocniki formatowania dat/godzin (zgodne z poprzednią aplikacją).

// 2026-06-01 -> 01.06.2026
export const ddmmyyyy = (iso) => (iso || '').split('-').reverse().join('.')

// "08:00:00" -> "08:00"
export const hhmm = (t) => (t ? String(t).slice(0, 5) : '')

// Godziny dziesiętne -> "HH:MM" (np. 8.5 -> "08:30", 160 -> "160:00")
export const godzinyHM = (h) => {
  const total = Math.max(0, Math.round((Number(h) || 0) * 60))
  const hh = Math.floor(total / 60)
  const mm = total % 60
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

// Kwota -> "240,00 zł"
export const zl = (n) =>
  new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'PLN', minimumFractionDigits: 2 }).format(Number(n) || 0)

// hex (#rrggbb) -> NIEPRZEZROCZYSTE tło komórki: kolor zmieszany z ciemną bazą.
// Dzięki temu działa też na „przyklejonych" kolumnach (nic nie prześwituje).
export const tloKoloru = (hex, alpha = 0.28) => {
  if (!hex || hex[0] !== '#' || hex.length < 7) return undefined
  const base = 18 // ciemna baza (~#121212)
  const mix = (i) => Math.round(parseInt(hex.slice(i, i + 2), 16) * alpha + base * (1 - alpha))
  return `rgb(${mix(1)}, ${mix(3)}, ${mix(5)})`
}

// Stała paleta — każde stanowisko dostaje swój kolor (liczony z nazwy, więc zawsze ten sam).
const PALETA_STAN = ['#34d399', '#f4e2a0', '#f2b8cb', '#60a5fa', '#a78bfa', '#fb923c', '#22d3ee', '#f87171']
export const kolorStanowiska = (nazwa) => {
  let h = 0
  for (let i = 0; i < (nazwa || '').length; i++) h = (h * 31 + nazwa.charCodeAt(i)) >>> 0
  return PALETA_STAN[h % PALETA_STAN.length]
}

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
