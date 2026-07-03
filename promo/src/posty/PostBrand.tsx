// Post 1/… karuzeli Instagram (1080×1350, statyczny): otwarcie brandowe.
// Logo + nazwa, obietnica w dwóch wierszach, pasek trzech cichych faktów.
import type { FC } from 'react'
import { C, F } from '../theme'
import { LogoMark } from '../components/LogoMark'
import { Tlo } from './Tlo'

const FAKTY = ['25+ modułów', '500+ testów', '0% prowizji']

export const PostBrand: FC = () => (
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
      {/* Znak + nazwa */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 34, marginTop: 26 }}>
        <LogoMark size={200} />
        <span
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 110,
            color: C.ink,
            letterSpacing: '-0.03em',
            lineHeight: 1,
          }}
        >
          Lokalo
        </span>
      </div>

      {/* Obietnica */}
      <div style={{ textAlign: 'center' }}>
        <div
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 100,
            letterSpacing: '-0.03em',
            lineHeight: 1.08,
            color: C.ink,
          }}
        >
          Cały lokal
        </div>
        <div
          style={{
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 100,
            letterSpacing: '-0.03em',
            lineHeight: 1.08,
            color: C.zloto2,
          }}
        >
          w jednym systemie.
        </div>
        <div style={{ marginTop: 30, fontFamily: F.body, fontWeight: 400, fontSize: 34, color: C.muted }}>
          Zamiast Excela, papieru i pięciu apek.
        </div>
      </div>

      {/* Pasek cichych faktów (zamiast sygnatury — logo jest już na górze) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 26 }}>
        {FAKTY.map((f, i) => (
          <span key={f} style={{ display: 'flex', alignItems: 'center', gap: 26 }}>
            {i > 0 && <span style={{ color: C.zloto, fontSize: 30, fontFamily: F.body }}>·</span>}
            <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.ink }}>{f}</span>
          </span>
        ))}
      </div>
    </div>
  </Tlo>
)
