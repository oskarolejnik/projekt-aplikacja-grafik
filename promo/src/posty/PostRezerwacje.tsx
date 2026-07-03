// Post IG 4:5 — REZERWACJE: widget rezerwacji w stanie końcowym (start=-100),
// nagłówek z obietnicą „0% prowizji". Statyczny still — zero hooków.
import type { FC } from 'react'
import { RezerwacjaOkno } from '../components/Okna'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Tlo } from './Tlo'

export const PostRezerwacje: FC = () => (
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
          Rezerwacje online.
        </div>
        <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 104, color: C.zloto2, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
          0% prowizji.
        </div>
      </div>

      {/* Wizual: okno rezerwacji w stanie końcowym */}
      <div style={{ flex: 1, display: 'grid', placeItems: 'center' }}>
        <div style={{ transform: 'scale(1.28)', transformOrigin: 'center' }}>
          <RezerwacjaOkno w={660} start={-100} />
        </div>
      </div>

      {/* Podpis + sygnatura */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 36 }}>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 32, color: C.muted }}>
          widget na Twojej stronie · SMS + e-mail · CRM gościa
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <LogoMark size={64} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 40, color: C.ink }}>Lokalo</span>
        </div>
      </div>
    </div>
  </Tlo>
)
