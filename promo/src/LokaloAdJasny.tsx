// Spot-teaser 9:16 v3 (1020 klatek @ 30 fps = 34 s, 1080×1920) — CZARNE tło,
// dynamika Apple-like slide-in od boku (naprzemiennie), równe rozmiary i
// pozycje (tytuły zawsze top 240). Historia: powiadomienia bólu → karteczka →
// auto-grafik → dyspozycyjność → pulpit właściciela/rezerwacje → telefon
// pracownika → wypłaty → puenta → brand. Sceny na siatce beatu (×15 kl.).
import type { FC } from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from 'remotion'
import {
  J1Powiadomienia, J2Karteczka, J3AutoGrafik, J4Dyspozycje, J5Karuzela,
  J6Telefon, J7Wyplaty, J8Puenta, J9Brand,
} from './jasny/scenyJ'

const PLAN = [
  { od: 0, dur: 135, El: J1Powiadomienia }, // 4 równe powiadomienia z prawej (9 beatów)
  { od: 135, dur: 120, El: J2Karteczka },   // karteczka z lewej, 7 zadań (8)
  { od: 255, dur: 120, El: J3AutoGrafik },  // „auto" wciska się → kaskada (8)
  { od: 375, dur: 105, El: J4Dyspozycje },  // dyspozycyjność zaznacza się (7)
  { od: 480, dur: 150, El: J5Karuzela },    // pulpit PRO + rezerwacje (2×75) (10)
  { od: 630, dur: 120, El: J6Telefon },     // telefon pracownika + push (8)
  { od: 750, dur: 90, El: J7Wyplaty },      // wypłaty co do minuty (6)
  { od: 840, dur: 90, El: J8Puenta },       // puenta keynote-slide (6)
  { od: 930, dur: 90, El: J9Brand },        // brand-reveal (6)
]

export const DLUGOSC_JASNY = 1020

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
