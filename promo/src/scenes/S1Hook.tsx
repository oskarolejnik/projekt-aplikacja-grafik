// [0–3.5 s] Otwarcie: złota nitka → logo → hasło. Spokojnie, po applowsku —
// wszystko pojawia się na miejscu (fade + scale), nic nie wjeżdża z boków.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, pojaw, SMOOTH } from '../helpers/anim'
import { Kinetic } from '../components/Kinetic'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S1Hook: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const nitka = en(frame, 0, 22, SMOOTH)
  return (
    <Scena dur={dur}>
      {/* Złota nitka przecina scenę i gaśnie, gdy pojawia się logo */}
      <div
        style={{
          position: 'absolute',
          top: '38%',
          left: 0,
          right: 0,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${C.zloto}, transparent)`,
          transform: `scaleX(${nitka})`,
          opacity: 1 - en(frame, 34, 20),
        }}
      />
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 46 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 30, ...pojaw(frame, 8, 26) }}>
          <LogoMark size={128} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 96, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Cały lokal." size={128} delay={42} stagger={5} />
          <div style={{ height: 10 }} />
          <Kinetic text="Jeden system." size={128} delay={58} stagger={5} color={C.zloto2} />
        </div>
        <div style={pojaw(frame, 82, 20, 0.98)}>
          <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.muted }}>
            Zamiast Excela, papieru i pięciu apek.
          </span>
        </div>
      </AbsoluteFill>
    </Scena>
  )
}
