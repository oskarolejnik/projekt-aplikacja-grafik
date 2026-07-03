// [3.5–7.5 s] Produkt: okno grafiku i portfel POWIĘKSZAJĄ SIĘ na miejscu
// (żadnego latania z boków), pigułki zmian kaskadują, chip „auto" domyka.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { pojaw } from '../helpers/anim'
import { GrafikOkno, WyplataOkno } from '../components/Okna'
import { Kinetic } from '../components/Kinetic'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S2Produkt: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ position: 'relative', ...pojaw(frame, 4, 26) }}>
          <GrafikOkno w={1060} start={16} />
          {/* Portfel pracownika — druga warstwa, pojawia się chwilę później */}
          <div style={{ position: 'absolute', right: -140, bottom: -90, ...pojaw(frame, 26, 24, 0.93) }}>
            <WyplataOkno w={480} start={36} />
          </div>
        </div>
      </AbsoluteFill>
      <div style={{ position: 'absolute', left: 120, bottom: 90 }}>
        <Kinetic text="Grafik układa się sam." size={64} delay={48} stagger={4} align="left" />
        <div style={{ ...pojaw(frame, 74, 20, 0.99), marginTop: 12 }}>
          <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 26, color: C.muted }}>
            dyspozycyjność → obsada z kwalifikacji → publikacja
          </span>
        </div>
      </div>
    </Scena>
  )
}
