import type { FC } from 'react'
import { Composition } from 'remotion'
import { DLUGOSC, LokaloAd } from './LokaloAd'

export const RemotionRoot: FC = () => (
  <Composition id="LokaloAd" component={LokaloAd} durationInFrames={DLUGOSC} fps={30} width={1920} height={1080} />
)
