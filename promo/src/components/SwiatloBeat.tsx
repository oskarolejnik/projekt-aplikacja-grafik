// Światło sceny oddychające w takcie (120 BPM → takt = 60 klatek @ 30 fps).
// Bardzo subtelne (±10% intensywności) — scena „żyje" z muzyką bez stroboskopu.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

export const SwiatloBeat: FC<{ gradient: string }> = ({ gradient }) => {
  const frame = useCurrentFrame()
  // Szczyt tuż po „raz" taktu (przesunięcie 6 kl.), pełny cykl = takt (2 s).
  const puls = 0.9 + 0.1 * Math.sin(((frame - 6) / 60) * Math.PI * 2)
  return <AbsoluteFill style={{ background: gradient, opacity: puls }} />
}
