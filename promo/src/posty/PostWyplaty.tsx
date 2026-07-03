// Post karuzeli Instagram (1080×1350, statyczny): moduł WYPŁATY.
// Okno wypłaty w stanie końcowym (start={-100}) — liczniki pokazują pełne kwoty.
import type { FC } from 'react'
import { C, F } from '../theme'
import { WyplataOkno } from '../components/Okna'
import { LogoMark } from '../components/LogoMark'
import { Tlo } from './Tlo'

export const PostWyplaty: FC = () => (
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
          Wypłaty
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
          co do minuty.
        </div>
      </div>

      {/* Wizual: okno wypłaty w stanie końcowym */}
      <div style={{ transform: 'scale(1.35)', transformOrigin: 'center' }}>
        <WyplataOkno w={640} start={-100} />
      </div>

      {/* Podpis + sygnatura */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 32, color: C.muted, textAlign: 'center' }}>
          RCP → godziny → kwota · portfel pracownika na żywo
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <LogoMark size={64} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 40, color: C.ink }}>Lokalo</span>
        </div>
      </div>
    </div>
  </Tlo>
)
