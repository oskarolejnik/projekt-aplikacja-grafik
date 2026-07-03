// Rama sceny PIONOWEJ: kamera jedzie w osi Y (mobile-native), wejścia i wyjścia
// szybsze niż w wersji kinowej (retencja > oddech). Wyjście: punch-zoom 6 klatek.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { kamera, wyjscie } from '../helpers/anim'

type Props = {
  dur: number
  odSkali?: number
  doSkali?: number
  panY?: number
  children: ReactNode
}

export const ScenaV: FC<Props> = ({ dur, odSkali = 1.04, doSkali = 1.12, panY = -26, children }) => {
  const frame = useCurrentFrame()
  return (
    <AbsoluteFill style={wyjscie(frame, dur, 6)}>
      <AbsoluteFill style={kamera(frame, dur, odSkali, doSkali, 0, panY)}>{children}</AbsoluteFill>
    </AbsoluteFill>
  )
}
