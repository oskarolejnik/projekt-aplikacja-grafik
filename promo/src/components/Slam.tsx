// Akcent tekstowy (dawny „slam", wyciszony na feedback): tekst POJAWIA SIĘ
// łagodnie ze skali 1.06→1 z fade — czytelny akcent bez agresji. Opcjonalne
// zejście (out) to czysty fade, bez skali i błysków.
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
  /** Klatka, od której tekst łagodnie znika (fade). */
  out?: number
}

export const Slam: FC<Props> = ({ text, size, delay = 0, dur = 18, color = C.ink, weight = 700, out }) => {
  const frame = useCurrentFrame()
  const t = en(frame, delay, dur)
  const o = out != null ? en(frame, out, 12) : 0
  return (
    <div
      style={{
        fontFamily: F.display,
        fontWeight: weight,
        fontSize: size,
        lineHeight: 1.04,
        letterSpacing: '-0.03em',
        color,
        textAlign: 'center',
        opacity: t * (1 - o),
        transform: `scale(${lerp(t, 1.06, 1)})`,
        filter: t < 0.8 ? `blur(${((1 - t) * 4).toFixed(1)}px)` : undefined,
      }}
    >
      {text}
    </div>
  )
}
