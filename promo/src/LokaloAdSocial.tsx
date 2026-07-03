// Montaż wersji SOCIAL 9:16 (450 klatek @ 30 fps = 15 s, 1080×1920).
// Szybciej niż wersja kinowa: hook w 1. sekundzie, beat co ~0,5–1 s, cięcia
// z mikro-błyskiem (punch), kamera zawsze w ruchu w osi Y.
import type { FC } from 'react'
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from 'remotion'
import { C } from './theme'
import { V1Hook, V2Grafik, V3Wyplaty, V4Rezerwacje, V5Pulpit, V6Cennik, V7Cta } from './social/scenyV'

const PLAN = [
  { od: 0, dur: 55, El: V1Hook },        // ból → logo → obietnica
  { od: 55, dur: 70, El: V2Grafik },     // grafik układa się sam
  { od: 125, dur: 65, El: V3Wyplaty },   // wypłaty co do minuty
  { od: 190, dur: 65, El: V4Rezerwacje },// rezerwacje 0%
  { od: 255, dur: 65, El: V5Pulpit },    // liczby na żywo
  { od: 320, dur: 70, El: V6Cennik },    // talia cen + zaufanie
  { od: 390, dur: 60, El: V7Cta },       // CTA
]

export const DLUGOSC_SOCIAL = 450

// Mikro-błysk w klatce cięcia — „punch" znany z edycji social, ale wyciszony
// (maks. 14% bieli, 5 klatek) — premium, nie strobo.
const Blysk: FC = () => {
  const frame = useCurrentFrame()
  const ciecia = PLAN.slice(1).map((p) => p.od)
  const moc = Math.max(
    ...ciecia.map((c) =>
      interpolate(frame, [c - 2, c, c + 3], [0, 0.14, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
    ),
  )
  if (moc <= 0) return null
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: `radial-gradient(70% 55% at 50% 46%, rgba(255,248,235,${moc}), transparent 75%)`,
      }}
    />
  )
}

export const LokaloAdSocial: FC = () => (
  <AbsoluteFill style={{ background: C.noc }}>
    {/* Światło sceny noir w pionie: złoto od góry, kontra od dołu */}
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(900px 700px at 50% -6%, rgba(201,169,106,0.08), transparent 62%),
          radial-gradient(800px 600px at 50% 108%, rgba(201,169,106,0.05), transparent 65%),
          radial-gradient(700px 500px at 90% 30%, rgba(255,255,255,0.035), transparent 60%)
        `,
      }}
    />
    {PLAN.map(({ od, dur, El }) => (
      <Sequence key={od} from={od} durationInFrames={dur}>
        <El dur={dur} />
      </Sequence>
    ))}
    <Blysk />
    {/* Winieta — delikatniejsza niż w kinowej (małe ekrany i tak przyciemniają) */}
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(110% 100% at 50% 50%, transparent 68%, rgba(0,0,0,0.42) 100%)',
      }}
    />
  </AbsoluteFill>
)
