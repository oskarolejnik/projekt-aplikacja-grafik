import type { FC } from 'react'
import { Composition } from 'remotion'
import { DLUGOSC, LokaloAd } from './LokaloAd'
import { DLUGOSC_SOCIAL, LokaloAdSocial } from './LokaloAdSocial'

export const RemotionRoot: FC = () => (
  <>
    <Composition id="LokaloAd" component={LokaloAd} durationInFrames={DLUGOSC} fps={30} width={1920} height={1080} />
    {/* Wersja social 9:16 — TikTok / Reels / Shorts / X */}
    <Composition id="LokaloAdSocial" component={LokaloAdSocial} durationInFrames={DLUGOSC_SOCIAL} fps={30} width={1080} height={1920} />
  </>
)
