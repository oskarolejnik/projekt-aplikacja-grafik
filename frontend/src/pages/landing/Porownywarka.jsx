import { Icon } from '../../lib/icons'

// Porównywarka pakietów: pełna macierz funkcje × plany, pogrupowana obszarami.
// Na desktopie nagłówek planów jest sticky (przykleja się pod nawigacją podczas
// przewijania tabeli); na mobile całość przewija się poziomo we własnym kontenerze.
// Nagłówki planów celowo NIE są <h3> — nagłówki-heading niosą karty cennika wyżej.

const PLANY = [
  { naz: 'Darmowy', cena: '0 zł' },
  { naz: 'Basic', cena: 'od 99 zł' },
  { naz: 'Pro', cena: 'od 199 zł', flagowy: true },
  { naz: 'Premium', cena: 'od 349 zł' },
  { naz: 'Enterprise', cena: 'wycena' },
]

// [etykieta, [Darmowy, Basic, Pro, Premium, Enterprise], opcje]
const GRUPY = [
  ['Grafik i zespół', [
    ['Grafik + dyspozycyjność zespołu', [1, 1, 1, 1, 1]],
    ['Giełda wymiany zmian', [1, 1, 1, 1, 1]],
    ['Auto-grafik z kwalifikacji', [0, 1, 1, 1, 1]],
    ['Strażnik prawa pracy (odpoczynek, limity)', [0, 1, 1, 1, 1]],
    ['Prognoza ruchu i obsady', [0, 0, 1, 1, 1]],
  ]],
  ['Czas pracy i wypłaty', [
    ['Ewidencja czasu pracy (RCP)', [0, 1, 1, 1, 1]],
    ['Raporty godzin → wypłaty co do minuty', [0, 1, 1, 1, 1]],
    ['Portfel pracownika + zaliczki', [0, 1, 1, 1, 1]],
    ['Napiwki: uczciwy podział puli', [0, 0, 0, 1, 1]],
  ]],
  ['Kasa i kontrola', [
    ['Rozliczenie dnia + zeszyt kasowy', [0, 0, 1, 1, 1]],
    ['Alerty anomalii kasowych', [0, 0, 1, 1, 1]],
    ['Zgodność: badania sanepid + terminy lokalu', [0, 0, 1, 1, 1]],
    ['Antyfraud POS: storna per kelner', [0, 0, 0, 0, 1]],
  ]],
  ['Goście i rezerwacje', [
    ['Rezerwacje stolików + plan sali', [0, 0, 1, 1, 1]],
    ['CRM gości ze scoringiem no-show', [0, 0, 1, 1, 1]],
    ['Rezerwacje online 0% prowizji', [0, 0, 0, 1, 1]],
  ]],
  ['Imprezy i wesela', [
    ['Kalendarz imprez + zadatki z kasy', [0, 0, 0, 1, 1]],
    ['Skrzynka zapytań o imprezy', [0, 0, 0, 1, 1], { ai: true }],
    ['Portal Pary Młodej: goście, menu, wpłaty', [0, 0, 0, 1, 1]],
  ]],
  ['Marka i skala', [
    ['White-label: Twoja marka i logo', [0, 0, 0, 1, 1]],
    ['Multi-lokal + SSO', [0, 0, 0, 0, 1]],
    ['SLA + umowa powierzenia (DPA)', [0, 0, 0, 0, 1]],
  ]],
]

const SIATKA = 'grid grid-cols-[minmax(220px,1.5fr)_repeat(5,minmax(96px,1fr))]'

export default function Porownywarka() {
  return (
    <div data-rv="" className="relative z-10 mx-auto mt-16 max-w-5xl">
      <h3 className="font-brand text-xl font-semibold text-ink sm:text-2xl">Porównaj pakiety funkcja po funkcji</h3>
      <p className="mt-1.5 text-sm text-muted">Każdy plan zawiera wszystko z poprzedniego. Moduły włączasz i wyłączasz jednym kliknięciem.</p>

      <div className="mt-6 overflow-x-auto pb-2 lg:overflow-visible">
        <div className="min-w-[720px] lg:min-w-0">
          {/* Nagłówek planów — sticky na desktopie, chowa się pod nawigację */}
          <div className={`${SIATKA} rounded-t-2xl border border-white/[0.08] bg-noc/85 backdrop-blur-xl lg:sticky lg:top-14 lg:z-20`}>
            <div className="px-4 py-3.5" />
            {PLANY.map((p) => (
              <div key={p.naz} className={`px-2 py-3.5 text-center ${p.flagowy ? 'bg-white/[0.05]' : ''}`}>
                <div className={`font-brand text-sm font-semibold ${p.flagowy ? 'text-zloto' : 'text-ink'}`}>{p.naz}</div>
                <div className="mt-0.5 text-[11px] tabular-nums text-muted">{p.cena}</div>
              </div>
            ))}
          </div>

          <div className="rounded-b-2xl border border-t-0 border-white/[0.08] bg-white/[0.02]">
            {GRUPY.map(([grupa, wiersze]) => (
              <div key={grupa}>
                <div className={`${SIATKA} border-b border-white/[0.06]`}>
                  <div className="col-span-6 px-4 pb-2 pt-5 text-[11px] font-semibold uppercase tracking-wider text-muted">{grupa}</div>
                </div>
                {wiersze.map(([cecha, kto, opcje]) => (
                  <div key={cecha} className={`${SIATKA} border-b border-white/[0.05] last:border-b-0`}>
                    <div className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink">
                      {opcje?.ai && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-fiolet/15 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-fiolet">
                          <Icon name="sparkles" className="h-2.5 w-2.5" /> AI
                        </span>
                      )}
                      <span className="leading-snug">{cecha}</span>
                    </div>
                    {kto.map((ma, i) => (
                      <div key={i} className={`grid place-items-center py-2.5 ${PLANY[i].flagowy ? 'bg-white/[0.03]' : ''}`}>
                        {ma
                          ? <Icon name="check" className={`h-4 w-4 ${PLANY[i].flagowy ? 'text-zloto' : 'text-mint'}`} />
                          : <span aria-hidden className="text-muted/40">—</span>}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
