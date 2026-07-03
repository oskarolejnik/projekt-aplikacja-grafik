// [22–25 s] Finał: logo, hasło, złote CTA z łagodnym przebiegiem światła.
import type { FC } from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion'
import { en, pojaw, SMOOTH } from '../helpers/anim'
import { Kinetic } from '../components/Kinetic'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S5Cta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const sheen = interpolate(frame, [50, 76], [-120, 420], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: SMOOTH })
  return (
    <Scena dur={dur}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 40 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, ...pojaw(frame, 2, 24) }}>
          <LogoMark size={104} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 76, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zbuduj przewagę operacyjną" size={76} delay={16} stagger={4} />
          <div style={{ height: 8 }} />
          <Kinetic text="swojego lokalu." size={76} delay={30} stagger={4} color={C.zloto2} />
        </div>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 20,
            background: C.zloto,
            padding: '22px 64px',
            ...pojaw(frame, 42, 20, 0.96),
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
              background: 'linear-gradient(105deg, transparent, rgba(255,255,255,0.5), transparent)',
              transform: 'skewX(-18deg)',
            }}
          />
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 22, color: C.muted, opacity: en(frame, 58, 16) }}>
          plan darmowy bez karty · start w kilka minut
        </span>
      </AbsoluteFill>
    </Scena>
  )
}
