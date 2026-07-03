// [0–2.5 s] Hook: złota nitka → logo → wielkie hasło.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, lerp, wjazd, SMOOTH } from '../helpers/anim'
import { Kinetic } from '../components/Kinetic'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S1Hook: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const nitka = en(frame, 0, 14, SMOOTH)
  const logo = en(frame, 4, 16)
  return (
    <Scena dur={dur} odSkali={1} doSkali={1.06}>
      {/* Złota nitka przecina scenę */}
      <div
        style={{
          position: 'absolute',
          top: '38%',
          left: 0,
          right: 0,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${C.zloto}, transparent)`,
          transform: `scaleX(${nitka})`,
          opacity: 1 - en(frame, 26, 14),
        }}
      />
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 44 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 30,
            transform: `scale(${lerp(logo, 0.55, 1)})`,
            opacity: logo,
            filter: logo < 0.9 ? `blur(${((1 - logo) * 12).toFixed(1)}px)` : undefined,
          }}
        >
          <LogoMark size={128} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 96, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Cały lokal." size={132} delay={34} stagger={4} />
          <div style={{ height: 10 }} />
          <Kinetic text="Jeden system." size={132} delay={44} stagger={4} color={C.zloto2} />
        </div>
        <div style={wjazd(frame, 58, 14, 'up', 40)}>
          <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.muted }}>
            Zamiast Excela, papieru i pięciu apek.
          </span>
        </div>
      </AbsoluteFill>
    </Scena>
  )
}
