// [2.5–5.7 s] Produkt: okno grafiku wjeżdża z paralaksą telefonu-portfela,
// pigułki zmian kaskadują, chip „auto" domyka historię.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { wjazd } from '../helpers/anim'
import { GrafikOkno, WyplataOkno } from '../components/Okna'
import { Kinetic } from '../components/Kinetic'
import { C, F } from '../theme'
import { Scena } from './Scena'

export const S2Produkt: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur} odSkali={1.05} doSkali={1.12} panX={-30} panY={-12}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ position: 'relative', ...wjazd(frame, 2, 20, 'right', 220) }}>
          <GrafikOkno w={1060} start={8} />
          {/* Paralaksa: mniejsze okno portfela na przednim planie, własny tor wejścia */}
          <div style={{ position: 'absolute', right: -140, bottom: -90, ...wjazd(frame, 16, 20, 'up', 160) }}>
            <WyplataOkno w={480} start={22} />
          </div>
        </div>
      </AbsoluteFill>
      <div style={{ position: 'absolute', left: 120, bottom: 90 }}>
        <Kinetic text="Grafik układa się sam." size={64} delay={26} align="left" />
        <div style={{ ...wjazd(frame, 40, 14, 'up', 30), marginTop: 12 }}>
          <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 26, color: C.muted }}>
            dyspozycyjność → obsada z kwalifikacji → publikacja
          </span>
        </div>
      </div>
    </Scena>
  )
}
