// Dodatkowe okna produktu dla teasera (feedback: automatyzacja grafiku,
// widok dyspozycji, rozbudowany pulpit właściciela, telefon pracownika).
// Ten sam język co components/Okna.tsx: rama Okno, mikrointerakcje w czasie.
import type { CSSProperties, FC } from 'react'
import { Fragment } from 'react'
import { useCurrentFrame } from 'remotion'
import { en, lerp, SNAP } from '../helpers/anim'
import { C, F } from '../theme'
import { Okno } from '../components/Okna'
import { Licznik } from '../components/Licznik'

const naglowek: CSSProperties = {
  fontFamily: F.display,
  fontWeight: 700,
  fontSize: 26,
  color: C.ink,
  letterSpacing: '-0.01em',
}
const mutedTxt: CSSProperties = { fontFamily: F.body, color: C.muted }

const DNI = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Ndz']

// ── Automatyzacja grafiku: puste sloty → „auto" wciska się → kaskada pigułek ──
const AUTO_ZMIANY: { kto: string; kolor: string; pas: number[] }[] = [
  { kto: 'AK', kolor: C.mint, pas: [1, 1, 0, 1, 2, 2, 0] },
  { kto: 'BN', kolor: C.lemon, pas: [0, 1, 1, 1, 2, 0, 2] },
  { kto: 'MR', kolor: C.blush, pas: [2, 0, 1, 0, 1, 2, 2] },
  { kto: 'JW', kolor: C.mint, pas: [1, 2, 0, 2, 0, 1, 1] },
]
const GODZ: Record<number, string> = { 1: '10–18', 2: '16–24' }

export const GrafikAutoOkno: FC<{ w?: number; start?: number }> = ({ w = 920, start = 0 }) => {
  const frame = useCurrentFrame()
  const klik = en(frame, start + 16, 8, SNAP)          // chip „auto" wciska się
  const wypelnianie = start + 28                        // od tej klatki pigułki wpadają
  return (
    <Okno w={w}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
        <span style={naglowek}>Grafik · przyszły tydzień</span>
        <span
          style={{
            fontFamily: F.body,
            fontWeight: 700,
            fontSize: 19,
            color: klik > 0.3 ? C.bg : C.mint,
            background: klik > 0.3 ? C.mint : 'rgba(157,196,177,0.15)',
            padding: '7px 18px',
            borderRadius: 99,
            transform: `scale(${1 - Math.sin(Math.min(klik, 1) * Math.PI) * 0.08})`,
          }}
        >
          ✦ auto
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `70px repeat(7, 1fr)`, gap: 8 }}>
        <div />
        {DNI.map((d) => (
          <div key={d} style={{ ...mutedTxt, fontWeight: 600, fontSize: 16, textAlign: 'center', paddingBottom: 4 }}>
            {d}
          </div>
        ))}
        {AUTO_ZMIANY.map((r, ri) => (
          <Fragment key={r.kto}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <span
                style={{
                  width: 44, height: 44, borderRadius: 99,
                  background: `${r.kolor}33`, color: r.kolor,
                  display: 'grid', placeItems: 'center',
                  fontFamily: F.body, fontWeight: 700, fontSize: 15,
                }}
              >
                {r.kto}
              </span>
            </div>
            {r.pas.map((v, ci) => {
              const t = en(frame, wypelnianie + (ri * 7 + ci) * 1.1, 9, SNAP)
              const kolor = v === 1 ? C.mint : C.lemon
              return (
                <div
                  key={ci}
                  style={{
                    height: 44, borderRadius: 12,
                    display: 'grid', placeItems: 'center',
                    fontFamily: F.body, fontWeight: 600, fontSize: 15,
                    background: v ? `${kolor}${Math.round(t * 38).toString(16).padStart(2, '0')}` : 'rgba(255,255,255,0.03)',
                    color: v ? kolor : 'transparent',
                    opacity: v ? Math.max(t, 0.25) : 0.6,
                    transform: `scale(${v ? lerp(t, 0.7, 1) : 1})`,
                  }}
                >
                  {t > 0.15 ? GODZ[v] ?? '' : ''}
                </div>
              )
            })}
          </Fragment>
        ))}
      </div>
    </Okno>
  )
}

// ── Dyspozycyjność pracownika: dni zaznaczają się same, wysyłka na końcu ──────
const DYSPO: { dzien: string; data: string; moge: boolean }[] = [
  { dzien: 'Poniedziałek', data: '7 lip', moge: true },
  { dzien: 'Wtorek', data: '8 lip', moge: true },
  { dzien: 'Środa', data: '9 lip', moge: false },
  { dzien: 'Czwartek', data: '10 lip', moge: true },
  { dzien: 'Piątek', data: '11 lip', moge: true },
  { dzien: 'Sobota', data: '12 lip', moge: true },
  { dzien: 'Niedziela', data: '13 lip', moge: false },
]

export const DyspozycjeOkno: FC<{ w?: number; start?: number }> = ({ w = 720, start = 0 }) => {
  const frame = useCurrentFrame()
  const wyslij = en(frame, start + 66, 8, SNAP)
  return (
    <Okno w={w}>
      <div style={{ ...naglowek, marginBottom: 18 }}>Twoja dyspozycyjność</div>
      <div style={{ display: 'grid', gap: 10 }}>
        {DYSPO.map((d, i) => {
          const t = en(frame, start + 10 + i * 7, 8, SNAP)
          const zaznaczone = t > 0.4
          return (
            <div
              key={d.dzien}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                borderRadius: 14, border: `1.5px solid ${C.line}`,
                background: 'rgba(255,255,255,0.02)', padding: '12px 18px',
              }}
            >
              <div>
                <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 21, color: C.ink }}>{d.dzien}</span>
                <span style={{ ...mutedTxt, fontSize: 18, marginLeft: 12 }}>{d.data}</span>
              </div>
              <span
                style={{
                  fontFamily: F.body, fontWeight: 700, fontSize: 17,
                  padding: '6px 16px', borderRadius: 99,
                  background: zaznaczone ? (d.moge ? 'rgba(157,196,177,0.2)' : 'rgba(255,255,255,0.06)') : 'rgba(255,255,255,0.03)',
                  color: zaznaczone ? (d.moge ? C.mint : C.muted) : 'transparent',
                  transform: `scale(${lerp(Math.min(t, 1), 0.8, 1)})`,
                }}
              >
                {d.moge ? 'mogę' : 'nie mogę'}
              </span>
            </div>
          )
        })}
      </div>
      <div
        style={{
          marginTop: 18, borderRadius: 14, background: C.cream, textAlign: 'center',
          padding: '13px 0', fontFamily: F.body, fontWeight: 700, fontSize: 20, color: C.bg,
          transform: `scale(${1 - Math.sin(Math.min(wyslij, 1) * Math.PI) * 0.05})`,
          opacity: en(frame, start + 58, 10),
        }}
      >
        Wyślij do managera
      </div>
    </Okno>
  )
}

// ── Rozbudowany pulpit właściciela: 4 KPI + wykres + alerty ───────────────────
const SLUPKI = [42, 55, 48, 70, 96, 88, 61]

export const PulpitProOkno: FC<{ w?: number; start?: number }> = ({ w = 920, start = 0 }) => {
  const frame = useCurrentFrame()
  const max = Math.max(...SLUPKI)
  const kpi: [string, React.ReactNode, string][] = [
    ['Przychód', <Licznik key="a" do_={12480} start={start + 6} dur={30} sufiks=" zł" />, C.mint],
    ['Ruch', <Licznik key="b" do_={214} start={start + 10} dur={26} />, C.lemon],
    ['Koszt pracy', <Licznik key="c" do_={3120} start={start + 14} dur={26} sufiks=" zł" />, C.blush],
    ['Rezerwacje', <Licznik key="d" do_={18} start={start + 18} dur={22} />, C.mint],
  ]
  const alerty: [string, string][] = [
    ['Wtorek: różnica kasowa −40 zł', C.lemon],
    ['Sobota: obsada kompletna (12/12)', C.mint],
  ]
  return (
    <Okno w={w}>
      <div style={{ ...naglowek, marginBottom: 20 }}>Pulpit właściciela</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {kpi.map(([l, v, k], i) => (
          <div
            key={l}
            style={{
              borderRadius: 16, border: `1.5px solid ${C.line}`, background: C.surface2,
              padding: '13px 16px', opacity: en(frame, start + i * 4, 12),
            }}
          >
            <div style={{ ...mutedTxt, fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{l}</div>
            <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 26, color: k, marginTop: 3, fontVariantNumeric: 'tabular-nums' }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, height: 110, marginTop: 22 }}>
        {SLUPKI.map((s, i) => {
          const t = en(frame, start + 14 + i * 2.2, 18)
          return (
            <div
              key={i}
              style={{
                flex: 1, borderRadius: '7px 7px 0 0', background: C.mint,
                height: `${(s / max) * 100 * t}%`, opacity: 0.55 + (s / max) * 0.45,
              }}
            />
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
        {DNI.map((d) => (
          <span key={d} style={{ ...mutedTxt, fontSize: 13 }}>{d}</span>
        ))}
      </div>
      <div style={{ display: 'grid', gap: 9, marginTop: 18 }}>
        {alerty.map(([txt, kolor], i) => (
          <div
            key={txt}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              borderRadius: 13, border: `1.5px solid ${C.line}`, background: 'rgba(255,255,255,0.02)',
              padding: '10px 16px', opacity: en(frame, start + 34 + i * 8, 12),
            }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 99, background: kolor, flexShrink: 0 }} />
            <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 19, color: C.ink }}>{txt}</span>
          </div>
        ))}
      </div>
    </Okno>
  )
}

// ── Telefon pracownika: rama + push + najbliższe zmiany ───────────────────────
const ZMIANY_TEL: { dzien: string; godz: string; gdzie: string }[] = [
  { dzien: 'Piątek', godz: '10–18', gdzie: 'Sala' },
  { dzien: 'Sobota', godz: '16–24', gdzie: 'Wesele · sala złota' },
  { dzien: 'Niedziela', godz: '—', gdzie: 'wolne' },
]

export const Telefon: FC<{ w?: number; start?: number }> = ({ w = 460, start = 0 }) => {
  const frame = useCurrentFrame()
  const push = en(frame, start + 12, 16)
  const h = w * 2.05
  return (
    <div
      style={{
        width: w, height: h, borderRadius: w * 0.16,
        border: '2px solid rgba(255,255,255,0.16)',
        background: '#101013',
        boxShadow: '0 40px 110px -30px rgba(0,0,0,0.8)',
        padding: w * 0.035, position: 'relative', overflow: 'hidden',
      }}
    >
      {/* notch */}
      <div style={{ position: 'absolute', top: w * 0.045, left: '50%', transform: 'translateX(-50%)', width: w * 0.3, height: w * 0.045, borderRadius: 99, background: 'rgba(255,255,255,0.1)' }} />
      <div style={{ height: '100%', borderRadius: w * 0.12, background: C.bg, padding: `${w * 0.14}px ${w * 0.06}px ${w * 0.06}px`, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* push wjeżdża z góry ekranu */}
        <div
          style={{
            display: 'flex', gap: 10, alignItems: 'center',
            background: 'rgba(255,255,255,0.95)', borderRadius: 16, padding: '12px 14px',
            transform: `translateY(${lerp(push, -90, 0)}px)`, opacity: push,
          }}
        >
          <div style={{ width: 34, height: 34, borderRadius: 9, overflow: 'hidden', flexShrink: 0 }}>
            <svg viewBox="0 0 64 64" width="34" height="34" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="lokaloTileTel" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#A7D7C5" />
                  <stop offset="0.52" stopColor="#F4E2A0" />
                  <stop offset="1" stopColor="#F2A2A2" />
                </linearGradient>
              </defs>
              <rect width="64" height="64" rx="15" fill="url(#lokaloTileTel)" />
              <path d="M21 16 H28.5 V41 H45 V48.5 H21 Z" fill="#1C1C1E" />
              <circle cx="43.5" cy="21.5" r="4.6" fill="#1C1C1E" />
            </svg>
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: F.body, fontWeight: 700, fontSize: 16, color: '#17181C' }}>Lokalo</div>
            <div style={{ fontFamily: F.body, fontSize: 15, color: '#6B6F76' }}>Nowy grafik opublikowany</div>
          </div>
        </div>
        <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 24, color: C.ink, marginTop: 6 }}>Twoje zmiany</div>
        <div style={{ display: 'grid', gap: 10 }}>
          {ZMIANY_TEL.map((z, i) => (
            <div
              key={z.dzien}
              style={{
                borderRadius: 14, border: `1.5px solid ${C.line}`, background: C.surface2,
                padding: '12px 16px', opacity: en(frame, start + 26 + i * 6, 12),
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 18, color: C.ink }}>{z.dzien}</span>
                <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 18, color: z.godz === '—' ? C.muted : C.mint, fontVariantNumeric: 'tabular-nums' }}>{z.godz}</span>
              </div>
              <div style={{ ...mutedTxt, fontSize: 15, marginTop: 2 }}>{z.gdzie}</div>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            borderRadius: 14, background: 'rgba(157,196,177,0.1)', padding: '12px 16px',
            opacity: en(frame, start + 48, 12),
          }}
        >
          <span style={{ ...mutedTxt, fontWeight: 600, fontSize: 16 }}>Zarobione w lipcu</span>
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 20, color: C.mint, fontVariantNumeric: 'tabular-nums' }}>
            <Licznik do_={2140} start={start + 52} dur={22} sufiks=" zł" />
          </span>
        </div>
      </div>
    </div>
  )
}
