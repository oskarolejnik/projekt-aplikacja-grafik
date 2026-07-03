import { Icon } from '../../lib/icons'

// Winiety realnego UI produktu — „pokaż, nie opowiadaj". Budowane w kodzie na ciemnym
// motywie z pastelowym akcentem. Dekoracyjne (aria-hidden) — treść sprzedażowa jest w copy.
// Wszystkie trzymają się tokenów DESIGN.md: bg/surface/line/ink/muted + mięta/cytryna/róż.

const okno = 'rounded-2xl border border-line bg-surface-grad shadow-soft'
const pasekOkna = (
  <div className="flex items-center gap-1.5 border-b border-line px-4 py-3">
    <span className="h-2.5 w-2.5 rounded-full bg-coral/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-lemon/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-mint/70" />
  </div>
)

// — Grafik tygodnia: wiersze pracowników × dni, kolorowe pigułki zmian —
const DNI = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Ndz']
const ZMIANY = [
  { kto: 'AK', kolor: 'mint', pas: [1, 1, 0, 1, 2, 2, 0] },
  { kto: 'BN', kolor: 'lemon', pas: [0, 1, 1, 1, 2, 0, 2] },
  { kto: 'MR', kolor: 'blush', pas: [2, 0, 1, 0, 1, 2, 2] },
  { kto: 'JW', kolor: 'mint', pas: [1, 2, 0, 2, 0, 1, 1] },
]
const PILL = {
  0: 'bg-white/[0.03] text-transparent',
  1: 'bg-mint/15 text-mint',
  2: 'bg-lemon/15 text-lemon',
}
const GODZ = { 1: '10–18', 2: '16–24' }
// Literalne klasy (Tailwind JIT nie widzi klas sklejanych w runtime — mapujemy jawnie).
const AVATAR = { mint: 'bg-mint/20 text-mint', lemon: 'bg-lemon/20 text-lemon', blush: 'bg-blush/20 text-blush' }
const TXT = { mint: 'text-mint', lemon: 'text-lemon', blush: 'text-blush' }
const DOT = { mint: 'bg-mint', lemon: 'bg-lemon', blush: 'bg-blush' }

export function GrafikVignette({ className = '' }) {
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="font-display text-sm font-bold text-ink">Grafik · ten tydzień</div>
          <span className="inline-flex items-center gap-1 rounded-full bg-mint/15 px-2 py-0.5 text-[10px] font-semibold text-mint">
            <Icon name="sparkles" className="h-3 w-3" /> auto
          </span>
        </div>
        <div className="grid grid-cols-[auto_repeat(7,1fr)] gap-1 text-[10px]">
          <div />
          {DNI.map((d) => (
            <div key={d} className="pb-1 text-center font-semibold text-muted">{d}</div>
          ))}
          {ZMIANY.map((r) => (
            <div key={r.kto} className="contents">
              <div className="flex items-center pr-1">
                <span className={`grid h-6 w-6 place-items-center rounded-full text-[9px] font-bold ${AVATAR[r.kolor]}`}>{r.kto}</span>
              </div>
              {r.pas.map((v, i) => (
                <div key={i} className={`grid h-6 place-items-center rounded-md text-[9px] font-semibold tabular-nums ${PILL[v]}`}>
                  {GODZ[v] || ''}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// — Pulpit: kafle KPI + mini-wykres przychodu dziennego —
const SLUPKI = [42, 55, 48, 70, 96, 88, 61]
export function PulpitVignette({ className = '' }) {
  const max = Math.max(...SLUPKI)
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-3 font-display text-sm font-bold text-ink">Pulpit właściciela</div>
        <div className="grid grid-cols-3 gap-2">
          {[['Przychód', '12 480 zł', 'mint'], ['Ruch', '214', 'lemon'], ['Koszt pracy', '3 120 zł', 'blush']].map(([l, v, k]) => (
            <div key={l} className="rounded-xl border border-line bg-surface-2 px-2.5 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-wide text-muted">{l}</div>
              <div className={`mt-0.5 font-display text-[13px] font-bold ${TXT[k]}`}>{v}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex h-16 items-end gap-1.5">
          {SLUPKI.map((s, i) => (
            <div key={i} className="flex-1 rounded-t bg-mint" style={{ height: `${Math.round((s / max) * 100)}%`, opacity: 0.55 + (s / max) * 0.45 }} />
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[9px] text-muted">
          {DNI.map((d) => <span key={d}>{d}</span>)}
        </div>
      </div>
    </div>
  )
}

// — Rezerwacja online: widget dla gościa —
export function RezerwacjaVignette({ className = '' }) {
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-3 font-display text-sm font-bold text-ink">Zarezerwuj stolik</div>
        <div className="mb-2 flex gap-1.5">
          {['Pt 12', 'Sob 13', 'Ndz 14'].map((d, i) => (
            <div key={d} className={`flex-1 rounded-lg border px-2 py-1.5 text-center text-[11px] font-semibold ${i === 1 ? 'border-transparent bg-mint text-bg' : 'border-line text-muted'}`}>{d}</div>
          ))}
        </div>
        <div className="mb-3 flex gap-1.5">
          {['18:00', '19:30', '20:00', '21:00'].map((t, i) => (
            <div key={t} className={`flex-1 rounded-lg border px-1 py-1.5 text-center text-[11px] font-semibold ${i === 2 ? 'border-mint/60 bg-mint/15 text-mint' : 'border-line text-muted'}`}>{t}</div>
          ))}
        </div>
        <div className="mb-3 flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2">
          <span className="text-[11px] text-muted">Liczba osób</span>
          <span className="flex items-center gap-3 text-ink">
            <span className="grid h-5 w-5 place-items-center rounded-full border border-line text-xs">−</span>
            <span className="font-display text-sm font-bold tabular-nums">4</span>
            <span className="grid h-5 w-5 place-items-center rounded-full border border-line text-xs">+</span>
          </span>
        </div>
        <div className="rounded-lg bg-cream py-2 text-center text-[11px] font-semibold text-bg">Rezerwuję</div>
        <div className="mt-2 flex items-center justify-center gap-1.5 text-[10px] text-mint">
          <Icon name="check" className="h-3 w-3" /> Potwierdzenie SMS + e-mail
        </div>
      </div>
    </div>
  )
}

// — Rozliczenie dnia: utarg POS vs kasa, różnica zero —
export function KasaVignette({ className = '' }) {
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="font-display text-sm font-bold text-ink">Rozliczenie dnia · piątek</div>
          <span className="rounded-full bg-mint/15 px-2 py-0.5 text-[10px] font-semibold text-mint">zamknięte</span>
        </div>
        <div className="space-y-1.5">
          {[['Utarg z POS', '8 420 zł'], ['Terminal (karty)', '5 210 zł'], ['Gotówka w kasie', '3 210 zł']].map(([l, v]) => (
            <div key={l} className="flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2 text-[11px]">
              <span className="text-muted">{l}</span>
              <span className="font-mono font-bold tabular-nums text-ink">{v}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-mint/[0.08] px-3 py-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-mint">
            <Icon name="check" className="h-3 w-3" /> Różnica
          </span>
          <span className="font-display text-sm font-bold tabular-nums text-mint">0 zł</span>
        </div>
        <div className="mt-2 px-1 text-[10px] text-muted">
          wtorek: różnica <span className="font-semibold text-lemon">−40 zł</span> → alert dla właściciela
        </div>
      </div>
    </div>
  )
}

// — Imprezy i wesela: najbliższe wydarzenia + zadatki —
const IMPREZY = [
  { co: 'Wesele · Ania i Paweł', kiedy: 'sob 11.07 · 120 gości', chip: 'zadatek ✓', ton: 'mint' },
  { co: 'Chrzciny · sala ogrodowa', kiedy: 'ndz 19.07 · 45 gości', chip: 'rata 2/3', ton: 'lemon' },
  { co: 'Kolacja firmowa', kiedy: 'pt 24.07 · 80 osób', chip: 'szkic AI', ton: 'fiolet' },
]
const CHIP_IMPREZY = {
  mint: 'bg-mint/15 text-mint',
  lemon: 'bg-lemon/15 text-lemon',
  fiolet: 'bg-fiolet/15 text-fiolet',
}
export function ImprezyVignette({ className = '' }) {
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-3 font-display text-sm font-bold text-ink">Najbliższe imprezy</div>
        <div className="space-y-1.5">
          {IMPREZY.map((im) => (
            <div key={im.co} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold text-ink">{im.co}</div>
                <div className="text-[10px] text-muted">{im.kiedy}</div>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${CHIP_IMPREZY[im.ton]}`}>{im.chip}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-mint/[0.08] px-3 py-2">
          <span className="text-[11px] font-semibold text-muted">Zadatki w kasie</span>
          <span className="font-display text-sm font-bold tabular-nums text-mint">6 500 zł</span>
        </div>
      </div>
    </div>
  )
}

// — Wypłata: godziny z RCP → kwota —
export function WyplataVignette({ className = '' }) {
  return (
    <div aria-hidden className={`${okno} ${className}`}>
      {pasekOkna}
      <div className="p-4 sm:p-5">
        <div className="mb-1 font-display text-sm font-bold text-ink">Twoje godziny · lipiec</div>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-3xl font-bold tabular-nums text-ink">168:30</span>
          <span className="text-[11px] text-muted">h</span>
        </div>
        <div className="mt-3 space-y-1.5">
          {[['Sala', '96:00', 'mint'], ['Bar', '48:30', 'lemon'], ['Impreza', '24:00', 'blush']].map(([l, h, k]) => (
            <div key={l} className="flex items-center gap-2 text-[11px]">
              <span className={`h-2 w-2 rounded-full ${DOT[k]}`} />
              <span className="flex-1 text-muted">{l}</span>
              <span className="font-mono font-bold tabular-nums text-ink">{h}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-mint/[0.08] px-3 py-2">
          <span className="text-[11px] font-semibold text-muted">Do wypłaty</span>
          <span className="font-display text-sm font-bold text-mint">4 380 zł</span>
        </div>
      </div>
    </div>
  )
}
