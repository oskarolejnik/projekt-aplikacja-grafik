// Post IG 4:5 — CENNIK: kolumna trzech kart planów (wzór KartaV ze spotu 9:16,
// tu w pełni statycznie — ceny wpisane na sztywno, bez liczników).
import type { FC } from 'react'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Tlo } from './Tlo'

const PLANY = [
  { naz: 'Basic', cena: 99, opis: '1 lokal, bez limitu osób' },
  { naz: 'Pro', cena: 199, opis: 'Standard dla restauracji', flagowy: true },
  { naz: 'Premium', cena: 349, opis: 'Domy weselne i eventowe' },
]

const Karta: FC<{ k: (typeof PLANY)[number] }> = ({ k }) => {
  const flag = !!k.flagowy
  return (
    <div
      style={{
        width: 880,
        borderRadius: 32,
        border: `2px solid ${flag ? 'rgba(201,169,106,0.5)' : C.line}`,
        background: flag ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.03)',
        padding: '30px 44px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 20,
        boxShadow: '0 30px 80px -30px rgba(0,0,0,0.8)',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 42, color: C.ink }}>{k.naz}</span>
          {flag && (
            <span
              style={{
                background: C.zloto,
                color: C.noc,
                fontFamily: F.body,
                fontWeight: 700,
                fontSize: 21,
                padding: '7px 18px',
                borderRadius: 99,
                whiteSpace: 'nowrap',
              }}
            >
              Najczęściej wybierany
            </span>
          )}
        </div>
        <div style={{ fontFamily: F.body, fontSize: 25, color: C.muted, marginTop: 4 }}>{k.opis}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexShrink: 0 }}>
        <span
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 76,
            color: flag ? C.zloto2 : C.ink,
            fontVariantNumeric: 'tabular-nums',
            letterSpacing: '-0.02em',
          }}
        >
          {k.cena}
        </span>
        <span style={{ fontFamily: F.body, fontSize: 26, color: C.muted }}>zł/mc</span>
      </div>
    </div>
  )
}

export const PostCennik: FC = () => (
  <Tlo>
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      {/* Nagłówek */}
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 92, color: C.ink, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
          Zacznij za darmo.
        </div>
        <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 72, color: C.muted, letterSpacing: '-0.03em', lineHeight: 1.2 }}>
          Rośnij, kiedy chcesz.
        </div>
      </div>

      {/* Wizual: kolumna trzech planów */}
      <div style={{ flex: 1, display: 'grid', placeItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 26, alignItems: 'center' }}>
          {PLANY.map((k) => (
            <Karta key={k.naz} k={k} />
          ))}
        </div>
      </div>

      {/* Podpis + sygnatura */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 36 }}>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 32, color: C.muted }}>
          ceny netto · płacisz za lokal, nie za osobę
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <LogoMark size={64} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 40, color: C.ink }}>Lokalo</span>
        </div>
      </div>
    </div>
  </Tlo>
)
