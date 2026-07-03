// Spot „jasny teaser" 9:16 (720 klatek @ 30 fps = 24 s, 1080×1920) — styl
// referencji app-promo: jasna pastelowa scena, pływające karty UI z wielkimi
// cieniami, kierunkowy motion blur, narracja przez elementy interfejsu,
// chaos → porządek → puenta typograficzna → brand-reveal na czerni.
// Sceny na siatce beatu (wielokrotności 15 kl. @ 120 BPM).
import type { FC } from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from 'remotion'
import { J1Powiadomienia, J2Karteczka, J3Chaos, J4Porzadek, J5Puenta, J6Brand } from './jasny/scenyJ'

const PLAN = [
  { od: 0, dur: 120, El: J1Powiadomienia }, // wieczór managera w powiadomieniach (8 beatów)
  { od: 120, dur: 120, El: J2Karteczka },   // karteczka „Jutro:" (8)
  { od: 240, dur: 135, El: J3Chaos },       // chaos pięciu miejsc (9)
  { od: 375, dur: 135, El: J4Porzadek },    // porządek: produkt (9)
  { od: 510, dur: 105, El: J5Puenta },      // puenta typograficzna (7)
  { od: 615, dur: 105, El: J6Brand },       // brand-reveal (7)
]

export const DLUGOSC_JASNY = 720

export const LokaloAdJasny: FC = () => (
  <AbsoluteFill style={{ background: '#F6F7FA' }}>
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
