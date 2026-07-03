import type { FC } from 'react'
import { Composition, Still } from 'remotion'
import { DLUGOSC, LokaloAd } from './LokaloAd'
import { DLUGOSC_SOCIAL, LokaloAdSocial } from './LokaloAdSocial'
import { PostBrand } from './posty/PostBrand'
import { PostGrafik } from './posty/PostGrafik'
import { PostWyplaty } from './posty/PostWyplaty'
import { PostRezerwacje } from './posty/PostRezerwacje'
import { PostCennik } from './posty/PostCennik'
import { PostCta } from './posty/PostCta'

export const RemotionRoot: FC = () => (
  <>
    <Composition id="LokaloAd" component={LokaloAd} durationInFrames={DLUGOSC} fps={30} width={1920} height={1080} />
    {/* Wersja social 9:16 — TikTok / Reels / Shorts / X */}
    <Composition id="LokaloAdSocial" component={LokaloAdSocial} durationInFrames={DLUGOSC_SOCIAL} fps={30} width={1080} height={1920} />
    {/* Karuzela Instagram 4:5 — statyczne posty (render: `remotion still <Id>`) */}
    <Still id="PostBrand" component={PostBrand} width={1080} height={1350} />
    <Still id="PostGrafik" component={PostGrafik} width={1080} height={1350} />
    <Still id="PostWyplaty" component={PostWyplaty} width={1080} height={1350} />
    <Still id="PostRezerwacje" component={PostRezerwacje} width={1080} height={1350} />
    <Still id="PostCennik" component={PostCennik} width={1080} height={1350} />
    <Still id="PostCta" component={PostCta} width={1080} height={1350} />
  </>
)
