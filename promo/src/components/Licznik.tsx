// Odliczająca liczba (pl-PL), jak PriceNum na landingu — expo-out, bez odbić.
import type { FC } from 'react'
import { useCurrentFrame } from 'remotion'
import { en } from '../helpers/anim'
import { zl } from '../theme'

type Props = {
  od?: number
  do_: number
  start?: number
  dur?: number
  sufiks?: string
  format?: (n: number) => string
}

export const Licznik: FC<Props> = ({ od = 0, do_, start = 0, dur = 30, sufiks = '', format = zl }) => {
  const frame = useCurrentFrame()
  const t = en(frame, start, dur)
  const v = od + (do_ - od) * t
  return (
    <>
      {format(v)}
      {sufiks}
    </>
  )
}
