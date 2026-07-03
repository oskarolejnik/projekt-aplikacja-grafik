// Spot-teaser 9:16 (720 klatek @ 30 fps = 24 s, 1080×1920) — CZARNE tło
// i dynamika Apple-like (feedback): elementy wjeżdżają OD BOKU z rozmyciem
// prędkości; zamiast chaosu — karuzela ekranów aplikacji (naprzemienne
// slide-iny). Narracja przez elementy UI, puenta, brand-reveal.
// Sceny na siatce beatu (wielokrotności 15 kl. @ 120 BPM).
import type { FC } from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from 'remotion'
import { J1Powiadomienia, J2Karteczka, J3Karuzela, J4Porzadek, J5Puenta, J6Brand } from './jasny/scenyJ'

const PLAN = [
  { od: 0, dur: 105, El: J1Powiadomienia }, // powiadomienia z prawej (7 beatów)
  { od: 105, dur: 105, El: J2Karteczka },   // karteczka z lewej (7)
  { od: 210, dur: 210, El: J3Karuzela },    // karuzela 3 ekranów × 70 kl. (14)
  { od: 420, dur: 120, El: J4Porzadek },    // grafik+portfel z obu boków (8)
  { od: 540, dur: 90, El: J5Puenta },       // puenta keynote-slide (6)
  { od: 630, dur: 90, El: J6Brand },        // brand-reveal (6)
]

export const DLUGOSC_JASNY = 720

export const LokaloAdJasny: FC = () => (
  <AbsoluteFill style={{ background: '#0C0C0E' }}>
    <Audio
      src={staticFile('beat.wav')}
      volume={(f) =>
        interpolate(f, [0, 20, DLUGOSC_JASNY - 50, DLUGOSC_JASNY - 4], [0, 0.7, 0.7, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      }
    />
    {PLAN.map(({ od, dur, El }) => (
      <Sequence key={od} from={od} durationInFrames={dur}>
        <El dur={dur} />
      </Sequence>
    ))}
  </AbsoluteFill>
)
