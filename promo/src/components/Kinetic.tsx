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
  dur = 22,
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
          <span
            key={i}
            style={{
              display: 'inline-block',
              fontFamily: font,
              fontWeight: weight,
              fontSize: size,
              lineHeight: 1.06,
              letterSpacing: '-0.025em',
              color,
              // Apple-like: łagodny unos + fade, bez wyskoku spod maski
              transform: `translateY(${lerp(t, size * 0.22, 0)}px)`,
              opacity: t,
              filter: t < 0.8 ? `blur(${((1 - t) * 4).toFixed(1)}px)` : undefined,
            }}
          >
            {s}
          </span>
        )
      })}
    </div>
  )
}
