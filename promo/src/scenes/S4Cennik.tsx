// [13.2–16 s] Cennik + zaufanie: trzy karty ze staggerem, Pro uniesione ze złotą
// odznaką, ceny odliczają; na dole pasek uczciwych liczb produktu.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, lerp, wjazd } from '../helpers/anim'
import { Licznik } from '../components/Licznik'
import { Kinetic } from '../components/Kinetic'
import { C, F } from '../theme'
import { Scena } from './Scena'

const PLANY = [
  { naz: 'Basic', cena: 99, opis: '1 lokal, bez limitu osób' },
  { naz: 'Pro', cena: 199, opis: 'Standard dla restauracji', flagowy: true },
  { naz: 'Premium', cena: 349, opis: 'Domy weselne i eventowe' },
]

const Karta: FC<{ plan: (typeof PLANY)[number]; i: number }> = ({ plan, i }) => {
  const frame = useCurrentFrame()
  const start = 8 + i * 6
  const t = en(frame, start, 18)
  const flag = !!plan.flagowy
  return (
    <div
      style={{
        width: 380,
        borderRadius: 30,
        border: `1.5px solid ${flag ? 'rgba(201,169,106,0.45)' : C.line}`,
        background: flag ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.03)',
        padding: '34px 36px',
        position: 'relative',
        transform: `translateY(${lerp(t, 140, flag ? -26 : 0)}px) scale(${flag ? lerp(t, 0.95, 1.04) : 1})`,
        opacity: t,
        filter: t < 0.9 ? `blur(${((1 - t) * 8).toFixed(1)}px)` : undefined,
        boxShadow: '0 40px 100px -40px rgba(0,0,0,0.8)',
      }}
    >
      {flag && (
        <span
          style={{
            position: 'absolute',
            top: -18,
            left: '50%',
            transform: 'translateX(-50%)',
            background: C.zloto,
            color: C.noc,
            fontFamily: F.body,
            fontWeight: 700,
            fontSize: 17,
            padding: '7px 20px',
            borderRadius: 99,
            whiteSpace: 'nowrap',
            opacity: en(frame, start + 12, 10),
          }}
        >
          Najczęściej wybierany
        </span>
      )}
      <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 28, color: C.ink }}>{plan.naz}</div>
      <div style={{ fontFamily: F.body, fontSize: 17, color: C.muted, marginTop: 2 }}>{plan.opis}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 22 }}>
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 74, color: C.ink, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
          <Licznik do_={plan.cena} start={start + 6} dur={22} />
        </span>
        <span style={{ fontFamily: F.body, fontSize: 20, color: C.muted }}>zł/mc</span>
      </div>
      <div style={{ fontFamily: F.body, fontSize: 16, color: C.muted, marginTop: 4 }}>rozliczane rocznie</div>
    </div>
  )
}

const TRUST = ['25+ modułów', '500+ testów automatycznych', '0% prowizji od rezerwacji']

export const S4Cennik: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur} odSkali={1.03} doSkali={1.08}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 54, paddingTop: 20 }}>
        <Kinetic text="Zacznij za darmo. Rośnij, kiedy chcesz." size={54} delay={0} stagger={2} />
        <div style={{ display: 'flex', gap: 30, alignItems: 'center' }}>
          {PLANY.map((p, i) => (
            <Karta key={p.naz} plan={p} i={i} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 54, alignItems: 'center' }}>
          {TRUST.map((t, i) => (
            <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 54, ...wjazd(frame, 40 + i * 6, 14, 'up', 36) }}>
              {i > 0 && <span style={{ color: C.zloto, fontSize: 26 }}>·</span>}
              <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 27, color: C.ink }}>{t}</span>
            </span>
          ))}
        </div>
      </AbsoluteFill>
    </Scena>
  )
}
