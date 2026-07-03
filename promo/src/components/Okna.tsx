// Okna produktu — winiety z homepage odtworzone 1:1 w kodzie i OŻYWIONE:
// pigułki grafiku kaskadują, KPI odliczają, słupki rosną, rezerwacja „sama się
// klika" (mikrointerakcje), wypłata nalicza się na oczach widza.
import type { CSSProperties, FC, ReactNode } from 'react'
import { Fragment } from 'react'
import { useCurrentFrame } from 'remotion'
import { en, lerp, SNAP } from '../helpers/anim'
import { C, F, zl } from '../theme'
import { Licznik } from './Licznik'

// ── Rama okna (pasek z kropkami jak na landingu) ──────────────────────────────
export const Okno: FC<{ w: number; children: ReactNode; style?: CSSProperties }> = ({ w, children, style }) => (
  <div
    style={{
      width: w,
      borderRadius: 28,
      border: `1.5px solid ${C.line}`,
      background: `linear-gradient(180deg, ${C.surface} 0%, #222225 100%)`,
      boxShadow: '0 40px 120px -40px rgba(0,0,0,0.85)',
      overflow: 'hidden',
      ...style,
    }}
  >
    <div style={{ display: 'flex', gap: 10, padding: '18px 24px', borderBottom: `1.5px solid ${C.line}` }}>
      {[C.coral, C.lemon, C.mint].map((k) => (
        <span key={k} style={{ width: 15, height: 15, borderRadius: 99, background: k, opacity: 0.7 }} />
      ))}
    </div>
    <div style={{ padding: 30 }}>{children}</div>
  </div>
)

const naglowek: CSSProperties = {
  fontFamily: F.display,
  fontWeight: 700,
  fontSize: 26,
  color: C.ink,
  letterSpacing: '-0.01em',
}
const mutedTxt: CSSProperties = { fontFamily: F.body, color: C.muted }

// ── Grafik tygodnia: pigułki zmian kaskadują wg indeksu ───────────────────────
const DNI = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Ndz']
const ZMIANY: { kto: string; kolor: string; pas: number[] }[] = [
  { kto: 'AK', kolor: C.mint, pas: [1, 1, 0, 1, 2, 2, 0] },
  { kto: 'BN', kolor: C.lemon, pas: [0, 1, 1, 1, 2, 0, 2] },
  { kto: 'MR', kolor: C.blush, pas: [2, 0, 1, 0, 1, 2, 2] },
  { kto: 'JW', kolor: C.mint, pas: [1, 2, 0, 2, 0, 1, 1] },
]
const GODZ: Record<number, string> = { 1: '10–18', 2: '16–24' }

export const GrafikOkno: FC<{ w?: number; start?: number }> = ({ w = 880, start = 0 }) => {
  const frame = useCurrentFrame()
  return (
    <Okno w={w}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
        <span style={naglowek}>Grafik · ten tydzień</span>
        <span
          style={{
            fontFamily: F.body,
            fontWeight: 700,
            fontSize: 18,
            color: C.mint,
            background: 'rgba(157,196,177,0.15)',
            padding: '6px 16px',
            borderRadius: 99,
            opacity: en(frame, start + 26, 10),
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
        {ZMIANY.map((r, ri) => (
          <Fragment key={r.kto}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <span
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 99,
                  background: `${r.kolor}33`,
                  color: r.kolor,
                  display: 'grid',
                  placeItems: 'center',
                  fontFamily: F.body,
                  fontWeight: 700,
                  fontSize: 15,
                }}
              >
                {r.kto}
              </span>
            </div>
            {r.pas.map((v, ci) => {
              const t = en(frame, start + 6 + (ri * 7 + ci) * 1.3, 10, SNAP)
              const kolor = v === 1 ? C.mint : C.lemon
              return (
                <div
                  key={ci}
                  style={{
                    height: 44,
                    borderRadius: 12,
                    display: 'grid',
                    placeItems: 'center',
                    fontFamily: F.body,
                    fontWeight: 600,
                    fontSize: 15,
                    background: v ? `${kolor}26` : 'rgba(255,255,255,0.03)',
                    color: v ? kolor : 'transparent',
                    transform: `scale(${v ? lerp(t, 0.6, 1) : 1})`,
                    opacity: v ? t : 0.6,
                  }}
                >
                  {GODZ[v] ?? ''}
                </div>
              )
            })}
          </Fragment>
        ))}
      </div>
    </Okno>
  )
}

// ── Pulpit właściciela: KPI odliczają, słupki rosną ───────────────────────────
const SLUPKI = [42, 55, 48, 70, 96, 88, 61]

export const PulpitOkno: FC<{ w?: number; start?: number }> = ({ w = 880, start = 0 }) => {
  const frame = useCurrentFrame()
  const max = Math.max(...SLUPKI)
  const kpi: [string, ReactNode, string][] = [
    ['Przychód', <Licznik key="a" do_={12480} start={start + 6} dur={34} sufiks=" zł" />, C.mint],
    ['Ruch', <Licznik key="b" do_={214} start={start + 10} dur={30} />, C.lemon],
    ['Koszt pracy', <Licznik key="c" do_={3120} start={start + 14} dur={30} sufiks=" zł" />, C.blush],
  ]
  return (
    <Okno w={w}>
      <div style={{ ...naglowek, marginBottom: 22 }}>Pulpit właściciela</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {kpi.map(([l, v, k], i) => (
          <div
            key={l}
            style={{
              borderRadius: 18,
              border: `1.5px solid ${C.line}`,
              background: C.surface2,
              padding: '16px 20px',
              opacity: en(frame, start + i * 4, 12),
            }}
          >
            <div style={{ ...mutedTxt, fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{l}</div>
            <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 30, color: k, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150, marginTop: 30 }}>
        {SLUPKI.map((s, i) => {
          const t = en(frame, start + 14 + i * 2.4, 20)
          return (
            <div
              key={i}
              style={{
                flex: 1,
                borderRadius: '8px 8px 0 0',
                background: C.mint,
                height: `${(s / max) * 100 * t}%`,
                opacity: 0.55 + (s / max) * 0.45,
              }}
            />
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10 }}>
        {DNI.map((d) => (
          <span key={d} style={{ ...mutedTxt, fontSize: 14 }}>
            {d}
          </span>
        ))}
      </div>
    </Okno>
  )
}

// ── Rezerwacja gościa: interfejs „sam się klika" (mikrointerakcje) ─────────────
export const RezerwacjaOkno: FC<{ w?: number; start?: number }> = ({ w = 620, start = 0 }) => {
  const frame = useCurrentFrame()
  const wyborDnia = en(frame, start + 10, 8, SNAP)      // Sob 13 zaznacza się
  const wyborGodziny = en(frame, start + 24, 8, SNAP)   // 20:00 zaznacza się
  const cta = en(frame, start + 40, 6, SNAP)            // przycisk „wciska się"
  const ok = en(frame, start + 48, 10)
  return (
    <Okno w={w}>
      <div style={{ ...naglowek, marginBottom: 20 }}>Zarezerwuj stolik</div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        {['Pt 12', 'Sob 13', 'Ndz 14'].map((d, i) => {
          const sel = i === 1
          return (
            <div
              key={d}
              style={{
                flex: 1,
                textAlign: 'center',
                padding: '12px 0',
                borderRadius: 14,
                fontFamily: F.body,
                fontWeight: 700,
                fontSize: 19,
                border: `1.5px solid ${sel ? 'transparent' : C.line}`,
                background: sel ? `rgba(157,196,177,${wyborDnia})` : 'transparent',
                color: sel ? (wyborDnia > 0.5 ? C.bg : C.muted) : C.muted,
                transform: sel ? `scale(${1 + Math.sin(Math.min(wyborDnia, 1) * Math.PI) * 0.06})` : undefined,
              }}
            >
              {d}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        {['18:00', '19:30', '20:00', '21:00'].map((g, i) => {
          const sel = i === 2
          return (
            <div
              key={g}
              style={{
                flex: 1,
                textAlign: 'center',
                padding: '10px 0',
                borderRadius: 14,
                fontFamily: F.body,
                fontWeight: 700,
                fontSize: 18,
                border: `1.5px solid ${sel && wyborGodziny > 0.4 ? 'rgba(157,196,177,0.6)' : C.line}`,
                background: sel ? `rgba(157,196,177,${0.15 * wyborGodziny})` : 'transparent',
                color: sel && wyborGodziny > 0.4 ? C.mint : C.muted,
                transform: sel ? `scale(${1 + Math.sin(Math.min(wyborGodziny, 1) * Math.PI) * 0.06})` : undefined,
              }}
            >
              {g}
            </div>
          )
        })}
      </div>
      <div
        style={{
          borderRadius: 16,
          background: C.cream,
          textAlign: 'center',
          padding: '14px 0',
          fontFamily: F.body,
          fontWeight: 700,
          fontSize: 20,
          color: C.bg,
          transform: `scale(${1 - Math.sin(Math.min(cta, 1) * Math.PI) * 0.04})`,
        }}
      >
        Rezerwuję
      </div>
      <div
        style={{
          marginTop: 14,
          textAlign: 'center',
          fontFamily: F.body,
          fontWeight: 600,
          fontSize: 17,
          color: C.mint,
          opacity: ok,
          transform: `translateY(${lerp(ok, 8, 0)}px)`,
        }}
      >
        ✓ Potwierdzenie SMS + e-mail
      </div>
    </Okno>
  )
}

// ── Wypłata pracownika: godziny i kwota naliczają się na żywo ─────────────────
const fmtGodz = (h: number) => {
  const total = Math.round(h * 2) / 2
  const godz = Math.floor(total)
  const min = Math.round((total - godz) * 60)
  return `${godz}:${min.toString().padStart(2, '0')}`
}

export const WyplataOkno: FC<{ w?: number; start?: number }> = ({ w = 620, start = 0 }) => {
  const frame = useCurrentFrame()
  return (
    <Okno w={w}>
      <div style={{ ...naglowek, fontSize: 24, marginBottom: 6 }}>Twoje godziny · lipiec</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 84, color: C.ink, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
          <Licznik do_={168.5} od={0} start={start + 4} dur={36} format={fmtGodz} />
        </span>
        <span style={{ ...mutedTxt, fontSize: 22 }}>h</span>
      </div>
      <div style={{ marginTop: 18, display: 'grid', gap: 10 }}>
        {(
          [
            ['Sala', '96:00', C.mint],
            ['Bar', '48:30', C.lemon],
            ['Impreza', '24:00', C.blush],
          ] as const
        ).map(([l, g, k], i) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 12, opacity: en(frame, start + 16 + i * 5, 12) }}>
            <span style={{ width: 12, height: 12, borderRadius: 99, background: k }} />
            <span style={{ ...mutedTxt, fontSize: 19, flex: 1 }}>{l}</span>
            <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 19, color: C.ink, fontVariantNumeric: 'tabular-nums' }}>{g}</span>
          </div>
        ))}
      </div>
      <div
        style={{
          marginTop: 20,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderRadius: 16,
          background: 'rgba(157,196,177,0.1)',
          padding: '14px 20px',
        }}
      >
        <span style={{ ...mutedTxt, fontWeight: 600, fontSize: 19 }}>Do wypłaty</span>
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 28, color: C.mint, fontVariantNumeric: 'tabular-nums' }}>
          <Licznik do_={4380} start={start + 22} dur={26} sufiks=" zł" />
        </span>
      </div>
    </Okno>
  )
}

export { zl }
