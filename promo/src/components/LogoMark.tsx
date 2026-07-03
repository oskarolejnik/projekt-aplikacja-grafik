// Znak Lokalo odtworzony wektorowo (zaokrąglony kafel, ciepły gradient marki,
// glif „L·") — jedyne miejsce z gradientem, jak w DESIGN.md (gradient żyje w logo).
import type { FC } from 'react'
import { C, F } from '../theme'

export const LogoMark: FC<{ size?: number }> = ({ size = 120 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size * 0.24,
      background: `linear-gradient(135deg, ${C.zloto2} 0%, ${C.zloto} 55%, ${C.mint} 130%)`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      boxShadow: '0 24px 80px -24px rgba(0,0,0,0.8)',
    }}
  >
    <span
      style={{
        fontFamily: F.display,
        fontWeight: 700,
        fontSize: size * 0.56,
        lineHeight: 1,
        color: C.noc,
        letterSpacing: '-0.02em',
        transform: 'translateY(-2%)',
      }}
    >
      L<span style={{ fontSize: size * 0.3, verticalAlign: 'super' }}>·</span>
    </span>
  </div>
)
