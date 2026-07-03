// Montaż spotu (540 klatek @ 30 fps = 18 s, 1920×1080).
// Nic nie stoi w miejscu: każda scena ma własny ruch kamery, wejścia z blurem
// prędkości i wyjście zoom+fade; cięcia co 2–3 s.
import type { FC } from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from 'remotion'
import { C } from './theme'
import { SwiatloBeat } from './components/SwiatloBeat'
import { S1Hook } from './scenes/S1Hook'
import { S2Produkt } from './scenes/S2Produkt'
import { S3Pulpit, S3Rezerwacje, S3Wyplaty } from './scenes/S3Cechy'
import { S4Cennik } from './scenes/S4Cennik'
import { S5Cta } from './scenes/S5Cta'

// Plan montażowy (klatki) — 25 s, spokojne tempo (feedback: „za szybko"):
const PLAN = [
  { od: 0, dur: 105, El: S1Hook },        // otwarcie + logo + hasło
  { od: 105, dur: 120, El: S2Produkt },   // produkt: grafik + portfel
  { od: 225, dur: 105, El: S3Pulpit },    // liczby na żywo
  { od: 330, dur: 105, El: S3Rezerwacje },// rezerwacje 0%
  { od: 435, dur: 105, El: S3Wyplaty },   // wypłaty co do minuty
  { od: 540, dur: 120, El: S4Cennik },    // cennik + trust
  { od: 660, dur: 90, El: S5Cta },        // CTA + logo
]

export const DLUGOSC = 750

export const LokaloAd: FC = () => (
  <AbsoluteFill style={{ background: C.noc }}>
    {/* Ścieżka: własny syntezowany beat 120 BPM (scripts/beat.js) — cięcia scen
        leżą na siatce beatu (każda scena = wielokrotność 15 klatek). */}
    <Audio
      src={staticFile('beat.wav')}
      volume={(f) =>
        interpolate(f, [0, 20, DLUGOSC - 50, DLUGOSC - 4], [0, 0.8, 0.8, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      }
    />
    {/* Światło sceny noir oddycha w takcie: ciepły poblask złota + zimna kontra */}
    <SwiatloBeat
      gradient={`
        radial-gradient(1200px 800px at 18% -8%, rgba(201,169,106,0.07), transparent 62%),
        radial-gradient(900px 600px at 86% 6%, rgba(255,255,255,0.04), transparent 60%),
        radial-gradient(1400px 900px at 50% 115%, rgba(201,169,106,0.05), transparent 65%)
      `}
    />
    {PLAN.map(({ od, dur, El }) => (
      <Sequence key={od} from={od} durationInFrames={dur}>
        <El dur={dur} />
      </Sequence>
    ))}
    {/* Winieta filmowa na wierzchu — domyka „cinematic look" */}
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(120% 90% at 50% 50%, transparent 62%, rgba(0,0,0,0.5) 100%)',
      }}
    />
  </AbsoluteFill>
)
