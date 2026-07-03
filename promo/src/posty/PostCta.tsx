// Post IG 4:5 — CTA zamykający karuzelę: logo + obietnica + złota pigułka.
// Sygnatury na dole brak (logo jest na górze) — zamiast niej pasek faktów.
import type { FC } from 'react'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Tlo } from './Tlo'

const FAKTY = ['25+ modułów', '500+ testów', '0% prowizji']

export const PostCta: FC = () => (
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
      {/* Znak marki */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 26 }}>
        <LogoMark size={160} />
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 90, color: C.ink, letterSpacing: '-0.03em' }}>
          Lokalo
        </span>
      </div>

      {/* Obietnica + przycisk */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 48 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 96, color: C.ink, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
            Zbuduj przewagę
          </div>
          <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 96, color: C.zloto2, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
            swojego lokalu.
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28 }}>
          <div style={{ borderRadius: 26, background: C.zloto, padding: '28px 88px' }}>
            <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 42, color: C.noc }}>Zacznij za darmo</span>
          </div>
          <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.muted }}>
            plan darmowy · bez karty · 5 minut
          </span>
        </div>
      </div>

      {/* Pasek faktów (jak w PostBrand) */}
      <div style={{ display: 'flex', gap: 34, alignItems: 'center' }}>
        {FAKTY.map((t, i) => (
          <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 34 }}>
            {i > 0 && <span style={{ color: C.zloto, fontSize: 30 }}>·</span>}
            <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 34, color: C.ink }}>{t}</span>
          </span>
        ))}
      </div>
    </div>
  </Tlo>
)
