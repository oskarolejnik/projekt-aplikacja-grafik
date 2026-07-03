// Post karuzeli Instagram (1080×1350, statyczny): moduł GRAFIK.
// Okno produktu w stanie końcowym (start={-100} = wszystkie animacje na t=1).
import type { FC } from 'react'
import { C, F } from '../theme'
import { GrafikOkno } from '../components/Okna'
import { LogoMark } from '../components/LogoMark'
import { Tlo } from './Tlo'

export const PostGrafik: FC = () => (
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
        <div
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 104,
            letterSpacing: '-0.03em',
            lineHeight: 1.08,
            color: C.ink,
          }}
        >
          Grafik układa
        </div>
        <div
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 104,
            letterSpacing: '-0.03em',
            lineHeight: 1.08,
            color: C.zloto2,
          }}
        >
          się sam.
        </div>
      </div>

      {/* Wizual: okno grafiku w stanie końcowym */}
      <div style={{ transform: 'scale(1.1)', transformOrigin: 'center' }}>
        <GrafikOkno w={920} start={-100} />
      </div>

      {/* Podpis + sygnatura */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 32, color: C.muted, textAlign: 'center' }}>
          dyspozycyjność → obsada z kwalifikacji → publikacja
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <LogoMark size={64} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 40, color: C.ink }}>Lokalo</span>
        </div>
      </div>
    </div>
  </Tlo>
)
