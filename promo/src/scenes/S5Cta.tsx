// [16–18 s] Finał: logo, hasło przewagi operacyjnej, złote CTA z przebiegiem
// światła (sheen) — mocne, minimalne zakończenie.
import type { FC } from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion'
import { en, lerp, SMOOTH } from '../helpers/anim'
import { Kinetic } from '../components/Kinetic'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S5Cta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const logo = en(frame, 0, 16)
  const cta = en(frame, 26, 14)
  // Sheen: pasek światła przejeżdża przez złoty przycisk
  const sheen = interpolate(frame, [34, 52], [-120, 420], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: SMOOTH })
  return (
    <Scena dur={dur} odSkali={1} doSkali={1.05}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 40 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 24,
            transform: `scale(${lerp(logo, 0.7, 1)})`,
            opacity: logo,
          }}
        >
          <LogoMark size={104} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 76, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zbuduj przewagę operacyjną" size={76} delay={10} stagger={3} />
          <div style={{ height: 8 }} />
          <Kinetic text="swojego lokalu." size={76} delay={20} stagger={3} color={C.zloto2} />
        </div>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 20,
            background: C.zloto,
            padding: '22px 64px',
            transform: `translateY(${lerp(cta, 60, 0)}px)`,
            opacity: cta,
          }}
        >
          <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 32, color: C.noc }}>Zacznij za darmo</span>
          <span
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              width: 90,
              left: sheen,
              background: 'linear-gradient(105deg, transparent, rgba(255,255,255,0.55), transparent)',
              transform: 'skewX(-18deg)',
            }}
          />
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 22, color: C.muted, opacity: en(frame, 40, 12) }}>
          plan darmowy bez karty · start w kilka minut
        </span>
      </AbsoluteFill>
    </Scena>
  )
}
