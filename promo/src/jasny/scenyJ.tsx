// Sceny teasera 9:16 NA CZERNI (feedback: czarne tło + animacje Apple-like —
// elementy wjeżdżają OD BOKU i to buduje dynamikę): powiadomienia z prawej →
// karteczka z lewej → KARUZELA ekranów aplikacji (naprzemienne slide-iny) →
// grafik+portfel spotykają się z obu stron → puenta → brand.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, kamera, lerp, wjazd, wyjscie, SMOOTH } from '../helpers/anim'
import { GrafikOkno, PulpitOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { CiemnaScena, IkonaApki, J, Karteczka, Powiadomienie } from './komponenty'

const ScenaJ: FC<{ dur: number; odSkali?: number; doSkali?: number; panX?: number; panY?: number; children: ReactNode }> = ({
  dur, odSkali = 1.0, doSkali = 1.06, panX = 0, panY = 0, children,
}) => {
  const frame = useCurrentFrame()
  return (
    <AbsoluteFill style={wyjscie(frame, dur, 12)}>
      <AbsoluteFill style={kamera(frame, dur, odSkali, doSkali, panX, panY)}>{children}</AbsoluteFill>
    </AbsoluteFill>
  )
}

// ── J1 [0–3.5 s]: wieczór managera — powiadomienia wjeżdżają z PRAWEJ ─────────
export const J1Powiadomienia: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} panY={-16}>
      <CiemnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 34 }}>
          <div style={wjazd(frame, 6, 24, 'left', 340)}>
            <Powiadomienie
              ikona={<IkonaApki kolor="#1D6F42" glif="X" />}
              tytul="Excel"
              tresc="Skoroszyt GRAFIK_v7_OSTATECZNY jest zablokowany przez innego użytkownika"
              kiedy="21:40"
              w={880}
            />
          </div>
          <div style={wjazd(frame, 28, 24, 'left', 340)}>
            <Powiadomienie
              ikona={<IkonaApki kolor="#34C759" glif="A" />}
              tytul="Ania (sala)"
              tresc="Szefie, mogę się zamienić na sobotę? Kasia się zgadza"
              kiedy="21:52"
              w={840}
              style={{ transform: 'translateX(-22px)' }}
            />
          </div>
          <div style={wjazd(frame, 50, 24, 'left', 340)}>
            <Powiadomienie
              ikona={<IkonaApki kolor="#F5C84C" glif="W" ciemnyGlif />}
              tytul="Kalendarz"
              tresc="Wesele 120 os. — potwierdzić menu i zadatek do piątku"
              kiedy="22:05"
              w={860}
              style={{ transform: 'translateX(18px)' }}
            />
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J2 [3.5–7 s]: karteczka „Jutro:" wjeżdża z LEWEJ ──────────────────────────
export const J2Karteczka: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  // Parallax: powiadomienie z poprzedniej sceny odpływa w prawo, w rozmycie.
  const odplyw = en(frame, 0, 30, SMOOTH)
  return (
    <ScenaJ dur={dur} odSkali={1.02} doSkali={1.08} panY={-12}>
      <CiemnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div
            style={{
              transform: `translate(${lerp(odplyw, -60, 240)}px, -560px) rotate(-4deg) scale(0.78)`,
              filter: 'blur(5px)',
              opacity: 0.45 * (1 - odplyw * 0.6),
            }}
          >
            <Powiadomienie ikona={<IkonaApki kolor="#1D6F42" glif="X" />} tytul="Excel" tresc="Skoroszyt jest zablokowany…" kiedy="21:40" w={640} />
          </div>
        </AbsoluteFill>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 4, 26, 'right', 380)}>
            <Karteczka
              data="pt, 3 lip"
              tytul="Jutro:"
              zadania={['ułożyć grafik na tydzień', 'policzyć godziny i wypłaty', 'oddzwonić: wesele 120 os.', 'sprawdzić utarg z wczoraj']}
              w={720}
            />
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J3 [7–14 s]: KARUZELA ekranów — naprzemienne slide-iny (Apple-like) ───────
// Każdy ekran: wjeżdża z boku z rozmyciem prędkości, chwilę „gra" (liczniki,
// mikrointerakcje), po czym miękko wyjeżdża w przeciwną stronę.
const EKRANY: { El: FC<{ w?: number; start?: number }>; w: number; skala: number; tytul: string; bok: 'lewy' | 'prawy' }[] = [
  { El: PulpitOkno, w: 880, skala: 1.06, tytul: 'Liczby lokalu. Na żywo.', bok: 'prawy' },
  { El: RezerwacjaOkno, w: 700, skala: 1.18, tytul: 'Rezerwacje online. 0% prowizji.', bok: 'lewy' },
  { El: WyplataOkno, w: 680, skala: 1.2, tytul: 'Wypłaty co do minuty.', bok: 'prawy' },
]
const SEGMENT = 70

export const J3Karuzela: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <CiemnaScena>
        {EKRANY.map((e, i) => {
          const od = i * SEGMENT
          const lokalna = frame - od
          if (lokalna < -10 || lokalna > SEGMENT + 24) return null
          const zPrawej = e.bok === 'prawy'
          const wej = en(frame, od + 2, 22)
          const wyj = i < EKRANY.length - 1 ? en(frame, od + SEGMENT - 10, 18, SMOOTH) : 0
          // Wjazd z jednego boku, wyjazd w przeciwny — ciągłość ruchu jak w keynote.
          const x = lerp(wej, zPrawej ? 420 : -420, 0) + lerp(wyj, 0, zPrawej ? -460 : 460)
          const blur = (1 - wej) * 12 + wyj * 10
          return (
            <AbsoluteFill key={e.tytul} style={{ alignItems: 'center', justifyContent: 'center' }}>
              <div
                style={{
                  transform: `translateX(${x}px) scale(${e.skala})`,
                  opacity: wej * (1 - wyj),
                  filter: blur > 0.5 ? `blur(${blur.toFixed(1)}px)` : undefined,
                }}
              >
                <e.El w={e.w} start={od + 14} />
              </div>
              <div
                style={{
                  position: 'absolute',
                  left: 40,
                  right: 40,
                  top: 260,
                  textAlign: 'center',
                  transform: `translateX(${x * 0.55}px)`,
                  opacity: Math.min(en(frame, od + 12, 16), 1 - wyj),
                }}
              >
                <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 54, color: J.jasnyInk, letterSpacing: '-0.02em' }}>
                  {e.tytul}
                </span>
              </div>
            </AbsoluteFill>
          )
        })}
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J4 [14–18 s]: grafik i portfel spotykają się z obu boków ──────────────────
export const J4Porzadek: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.07} panY={-10}>
      <CiemnaScena>
        <div style={{ position: 'absolute', left: 40, right: 40, top: 250, textAlign: 'center', ...wjazd(frame, 34, 20, 'left', 120) }}>
          <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 58, color: J.jasnyInk, letterSpacing: '-0.02em' }}>
            Aż wszystko trafia tutaj.
          </span>
        </div>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ position: 'relative' }}>
            <div style={wjazd(frame, 2, 26, 'left', 420)}>
              <GrafikOkno w={960} start={16} />
            </div>
            <div style={{ position: 'absolute', right: -30, bottom: -240, ...wjazd(frame, 18, 26, 'right', 420) }}>
              <WyplataOkno w={470} start={32} />
            </div>
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J5 [18–21 s]: puenta — białe boldy przesuwają się jak w keynote ───────────
export const J5Puenta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const zamiana = en(frame, 46, 16, SMOOTH)
  const wspolny = {
    fontFamily: F.body,
    fontWeight: 700 as const,
    fontSize: 88,
    color: J.jasnyInk,
    letterSpacing: '-0.03em',
    lineHeight: 1.08,
    textAlign: 'center' as const,
  }
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <CiemnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: '0 70px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <div
              style={{
                ...wspolny,
                position: 'absolute',
                left: 0,
                right: 0,
                top: '50%',
                transform: `translateY(-50%) translateX(${lerp(en(frame, 4, 22), -140, 0) + zamiana * 160}px)`,
                opacity: en(frame, 4, 22) * (1 - zamiana),
                filter: zamiana > 0.05 ? `blur(${(zamiana * 8).toFixed(1)}px)` : undefined,
              }}
            >
              Wszystko na swoim miejscu.
            </div>
            <div
              style={{
                ...wspolny,
                opacity: zamiana,
                transform: `translateX(${lerp(zamiana, -160, 0)}px)`,
                filter: zamiana < 0.85 ? `blur(${((1 - zamiana) * 8).toFixed(1)}px)` : undefined,
              }}
            >
              Cały lokal w jednym systemie.
            </div>
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J6 [21–24 s]: brand-reveal ────────────────────────────────────────────────
export const J6Brand: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const logo = en(frame, 4, 20)
  return (
    <AbsoluteFill style={{ background: '#0B0B0D', opacity: en(frame, 0, 8) }}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 44 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 30, opacity: logo, transform: `scale(${lerp(logo, 0.94, 1)})` }}>
          <LogoMark size={170} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 104, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 31, color: C.muted, opacity: en(frame, 26, 16) }}>
          Zacznij za darmo · plan darmowy bez karty
        </span>
      </AbsoluteFill>
    </AbsoluteFill>
  )
}
