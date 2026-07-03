// Rama sceny: powolny ruch „kamery" przez cały czas trwania + wyjście
// (zoom/fade/blur) w ostatnich klatkach — żadna scena nie stoi w miejscu.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { kamera, wyjscie } from '../helpers/anim'

type Props = {
  dur: number
  odSkali?: number
  doSkali?: number
  panX?: number
  panY?: number
  children: ReactNode
}

export const Scena: FC<Props> = ({ dur, odSkali = 1.02, doSkali = 1.08, panX = 0, panY = 0, children }) => {
  const frame = useCurrentFrame()
  return (
    <AbsoluteFill style={wyjscie(frame, dur)}>
      <AbsoluteFill style={kamera(frame, dur, odSkali, doSkali, panX, panY)}>{children}</AbsoluteFill>
    </AbsoluteFill>
  )
}
