// Montaż wersji SOCIAL 9:16 (600 klatek @ 30 fps = 20 s, 1080×1920).
// Tempo spokojne (feedback): sceny 2,5–3,7 s, cięcia jako czysty dissolve —
// bez błysków; jeden język ruchu: elementy powiększają się na miejscu.
import type { FC } from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from 'remotion'
import { C } from './theme'
import { SwiatloBeat } from './components/SwiatloBeat'
import { V1Hook, V2Grafik, V3Wyplaty, V4Rezerwacje, V5Pulpit, V6Cennik, V7Cta } from './social/scenyV'

// Każda scena = wielokrotność 15 klatek (beat @ 120 BPM) → cięcia zawsze w rytm.
const PLAN = [
  { od: 0, dur: 105, El: V1Hook },        // ból → logo → obietnica (7 beatów)
  { od: 105, dur: 90, El: V2Grafik },     // grafik układa się sam (6)
  { od: 195, dur: 90, El: V3Wyplaty },    // wypłaty co do minuty (6)
  { od: 285, dur: 90, El: V4Rezerwacje }, // rezerwacje 0% (6)
  { od: 375, dur: 75, El: V5Pulpit },     // liczby na żywo (5)
  { od: 450, dur: 90, El: V6Cennik },     // kolumna cen + zaufanie (6)
  { od: 540, dur: 60, El: V7Cta },        // CTA (4)
]

export const DLUGOSC_SOCIAL = 600

export const LokaloAdSocial: FC = () => (
  <AbsoluteFill style={{ background: C.noc }}>
    {/* Ścieżka: własny syntezowany beat 120 BPM — cięcia leżą na siatce beatu. */}
    <Audio
      src={staticFile('beat.wav')}
      volume={(f) =>
        interpolate(f, [0, 20, DLUGOSC_SOCIAL - 50, DLUGOSC_SOCIAL - 4], [0, 0.8, 0.8, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      }
    />
    {/* Światło sceny noir w pionie, oddycha w takcie */}
    <SwiatloBeat
      gradient={`
        radial-gradient(900px 700px at 50% -6%, rgba(201,169,106,0.08), transparent 62%),
        radial-gradient(800px 600px at 50% 108%, rgba(201,169,106,0.05), transparent 65%),
        radial-gradient(700px 500px at 90% 30%, rgba(255,255,255,0.035), transparent 60%)
      `}
    />
    {PLAN.map(({ od, dur, El }) => (
      <Sequence key={od} from={od} durationInFrames={dur}>
        <El dur={dur} />
      </Sequence>
    ))}
    {/* Winieta — delikatniejsza niż w kinowej (małe ekrany i tak przyciemniają) */}
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(110% 100% at 50% 50%, transparent 68%, rgba(0,0,0,0.42) 100%)',
      }}
    />
  </AbsoluteFill>
)
