// Typografia kinetyczna: słowa wjeżdżają kolejno spod linii (maska overflow),
// z lekkim rozmyciem prędkości. Zero odbić — czysty expo-out.
import type { FC } from 'react'
import { useCurrentFrame } from 'remotion'
import { en, lerp } from '../helpers/anim'
import { C, F } from '../theme'

type Props = {
  text: string
  size: number
  delay?: number
  stagger?: number
  dur?: number
  weight?: number
  color?: string
  font?: string
  align?: 'left' | 'center'
}

export const Kinetic: FC<Props> = ({
  text,
  size,
  delay = 0,
  stagger = 3,
  dur = 16,
  weight = 700,
  color = C.ink,
  font = F.display,
  align = 'center',
}) => {
  const frame = useCurrentFrame()
  const slowa = text.split(' ')
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: align === 'center' ? 'center' : 'flex-start',
        columnGap: size * 0.28,
        rowGap: size * 0.1,
      }}
    >
      {slowa.map((s, i) => {
        const t = en(frame, delay + i * stagger, dur)
        return (
          <span key={i} style={{ overflow: 'hidden', display: 'inline-block', paddingBottom: size * 0.08 }}>
            <span
              style={{
                display: 'inline-block',
                fontFamily: font,
                fontWeight: weight,
                fontSize: size,
                lineHeight: 1.04,
                letterSpacing: '-0.025em',
                color,
                transform: `translateY(${lerp(t, size * 1.15, 0)}px)`,
                opacity: Math.min(1, t * 1.6),
                filter: t < 0.9 ? `blur(${((1 - t) * 6).toFixed(1)}px)` : undefined,
              }}
            >
              {s}
            </span>
          </span>
        )
      })}
    </div>
  )
}
