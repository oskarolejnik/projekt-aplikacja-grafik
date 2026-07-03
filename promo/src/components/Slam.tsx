// Tekst-cios pod social: wpada ze skali 1.6 z rozmyciem i „dobija" do 1.0
// w ~9 klatek. Do hooków i haseł — czytelny na telefonie od pierwszej klatki.
import type { FC } from 'react'
import { useCurrentFrame } from 'remotion'
import { en, lerp } from '../helpers/anim'
import { C, F } from '../theme'

type Props = {
  text: string
  size: number
  delay?: number
  dur?: number
  color?: string
  weight?: number
  /** Klatka, od której tekst szybko znika (scale-down + blur). */
  out?: number
}

export const Slam: FC<Props> = ({ text, size, delay = 0, dur = 9, color = C.ink, weight = 700, out }) => {
  const frame = useCurrentFrame()
  const t = en(frame, delay, dur)
  const o = out != null ? en(frame, out, 7) : 0
  return (
    <div
      style={{
        fontFamily: F.display,
        fontWeight: weight,
        fontSize: size,
        lineHeight: 1.02,
        letterSpacing: '-0.03em',
        color,
        textAlign: 'center',
        opacity: t * (1 - o),
        transform: `scale(${lerp(t, 1.6, 1) * lerp(o, 1, 0.82)})`,
        filter: t < 0.85 || o > 0.1 ? `blur(${(((1 - t) + o) * 9).toFixed(1)}px)` : undefined,
      }}
    >
      {text}
    </div>
  )
}
