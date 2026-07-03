// Sceny spotu „jasny teaser" 9:16 (styl referencji app-promo): narracja przez
// elementy UI — ból w powiadomieniach → karteczka managera → chaos okien →
// porządek (produkt) → puenta typograficzna → brand-reveal na czerni.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, kamera, lerp, wjazd, wyjscie, SMOOTH } from '../helpers/anim'
import { GrafikOkno, PulpitOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { LogoMark } from '../components/LogoMark'
import { C, F } from '../theme'
import { IkonaApki, J, JasnaScena, Karteczka, Powiadomienie } from './komponenty'

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

// ── J1 [0–4 s]: piątkowy wieczór managera w trzech powiadomieniach ────────────
export const J1Powiadomienia: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} panY={-16}>
      <JasnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 34 }}>
          <div style={wjazd(frame, 6, 22, 'down', 160)}>
            <Powiadomienie
              ikona={<IkonaApki kolor="#1D6F42" glif="X" />}
              tytul="Excel"
              tresc="Skoroszyt GRAFIK_v7_OSTATECZNY jest zablokowany przez innego użytkownika"
              kiedy="21:40"
              w={880}
            />
          </div>
          <div style={wjazd(frame, 26, 22, 'down', 160)}>
            <Powiadomienie
              ikona={<IkonaApki kolor="#34C759" glif="A" />}
              tytul="Ania (sala)"
              tresc="Szefie, mogę się zamienić na sobotę? Kasia się zgadza"
              kiedy="21:52"
              w={840}
              style={{ transform: 'translateX(-22px)' }}
            />
          </div>
          <div style={wjazd(frame, 46, 22, 'down', 160)}>
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
      </JasnaScena>
    </ScenaJ>
  )
}

// ── J2 [4–8 s]: karteczka „na jutro" — analogowy system operacyjny lokalu ─────
export const J2Karteczka: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.03} doSkali={1.09} panY={-12}>
      <JasnaScena>
        {/* Tło-parallax: wieczorne powiadomienie ucieka w rozmycie */}
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ transform: 'translate(-90px, -560px) rotate(-5deg) scale(0.8)', filter: 'blur(5px)', opacity: 0.5 }}>
            <Powiadomienie ikona={<IkonaApki kolor="#1D6F42" glif="X" />} tytul="Excel" tresc="Skoroszyt jest zablokowany…" kiedy="21:40" w={640} />
          </div>
        </AbsoluteFill>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 4, 24, 'up', 180)}>
            <Karteczka
              data="pt, 3 lip"
              tytul="Jutro:"
              zadania={['ułożyć grafik na tydzień', 'policzyć godziny i wypłaty', 'oddzwonić: wesele 120 os.', 'sprawdzić utarg z wczoraj']}
              w={720}
            />
          </div>
        </AbsoluteFill>
      </JasnaScena>
    </ScenaJ>
  )
}

// ── J3 [8–12.5 s]: chaos — wszystko w pięciu miejscach naraz ──────────────────
const CHAOS: { x: number; y: number; s: number; r: number; b: number; El: FC<{ w?: number; start?: number }> }[] = [
  { x: -190, y: -560, s: 0.6, r: -7, b: 3, El: PulpitOkno },
  { x: 210, y: -300, s: 0.54, r: 6, b: 4, El: RezerwacjaOkno },
  { x: -230, y: 290, s: 0.5, r: 5, b: 5, El: WyplataOkno },
  { x: 210, y: 470, s: 0.48, r: -5, b: 2, El: GrafikOkno },
  { x: 0, y: -40, s: 0.66, r: 2, b: 0, El: GrafikOkno },
]

export const J3Chaos: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  // Konwergencja: pod koniec sceny okna ściągają do środka (zapowiedź porządku).
  const zbieg = en(frame, dur - 34, 26, SMOOTH)
  return (
    <ScenaJ dur={dur} odSkali={1.08} doSkali={1.0} panY={12}>
      <JasnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ position: 'relative' }}>
            {CHAOS.map((k, i) => {
              const t = en(frame, 4 + i * 6, 20)
              return (
                <div
                  key={i}
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    transform: `translate(-50%, -50%) translate(${lerp(zbieg, k.x, 0)}px, ${lerp(zbieg, k.y, 0)}px)
                      rotate(${lerp(zbieg, k.r, 0)}deg) scale(${lerp(zbieg, k.s, 0.4)})`,
                    opacity: t * (i === 4 ? 1 : 1 - zbieg * 0.9),
                    filter: k.b || zbieg > 0 ? `blur(${lerp(t, 8, k.b) + zbieg * 6}px)` : undefined,
                  }}
                >
                  <k.El w={820} start={-100} />
                </div>
              )
            })}
          </div>
        </AbsoluteFill>
        <div style={{ position: 'absolute', left: 40, right: 40, bottom: 210, textAlign: 'center', ...wjazd(frame, 34, 20, 'up', 44) }}>
          <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 56, color: J.ink, letterSpacing: '-0.02em' }}>
            Grafik. Wypłaty. Kasa. Wesela.
          </span>
          <div style={{ fontFamily: F.body, fontWeight: 600, fontSize: 36, color: J.muted, marginTop: 10 }}>
            Wszystko w pięciu miejscach naraz.
          </div>
        </div>
      </JasnaScena>
    </ScenaJ>
  )
}

// ── J4 [12.5–17 s]: porządek — produkt na scenie, pigułki kaskadują ───────────
export const J4Porzadek: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.07} panY={-12}>
      <JasnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ position: 'relative', ...wjazd(frame, 2, 22, 'zoom') }}>
            <div style={{ boxShadow: '0 60px 140px -30px rgba(23,24,28,0.38)', borderRadius: 28 }}>
              <GrafikOkno w={960} start={14} />
            </div>
            <div
              style={{
                position: 'absolute',
                right: -30,
                bottom: -240,
                boxShadow: '0 40px 100px -24px rgba(23,24,28,0.34)',
                borderRadius: 28,
                ...wjazd(frame, 22, 22, 'up', 140),
              }}
            >
              <WyplataOkno w={470} start={30} />
            </div>
          </div>
        </AbsoluteFill>
        <div style={{ position: 'absolute', left: 40, right: 40, top: 190, textAlign: 'center', ...wjazd(frame, 40, 20, 'down', 40) }}>
          <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 58, color: J.ink, letterSpacing: '-0.02em' }}>
            Aż trafia tutaj.
          </span>
        </div>
      </JasnaScena>
    </ScenaJ>
  )
}

// ── J5 [17–20.5 s]: puenta typograficzna (czarny bold na jasnym) ──────────────
export const J5Puenta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const zamiana = en(frame, 52, 14, SMOOTH)
  const wspolny = {
    fontFamily: F.body,
    fontWeight: 700 as const,
    fontSize: 88,
    color: J.ink,
    letterSpacing: '-0.03em',
    lineHeight: 1.08,
    textAlign: 'center' as const,
  }
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <JasnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: '0 70px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <div
              style={{
                ...wspolny,
                position: 'absolute',
                left: 0,
                right: 0,
                top: '50%',
                transform: `translateY(-50%) translateY(${lerp(en(frame, 6, 20), 44, 0)}px)`,
                opacity: en(frame, 6, 20) * (1 - zamiana),
              }}
            >
              Wszystko na swoim miejscu.
            </div>
            <div
              style={{
                ...wspolny,
                opacity: zamiana,
                transform: `translateY(${lerp(zamiana, 44, 0)}px)`,
              }}
            >
              Cały lokal w jednym systemie.
            </div>
          </div>
        </AbsoluteFill>
      </JasnaScena>
    </ScenaJ>
  )
}

// ── J6 [20.5–24 s]: brand-reveal na czerni ────────────────────────────────────
export const J6Brand: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const logo = en(frame, 6, 20)
  return (
    <AbsoluteFill style={{ background: '#0B0B0D', opacity: en(frame, 0, 10) }}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 44 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 30, opacity: logo, transform: `scale(${lerp(logo, 0.94, 1)})` }}>
          <LogoMark size={170} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 104, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 31, color: C.muted, opacity: en(frame, 28, 16) }}>
          Zacznij za darmo · plan darmowy bez karty
        </span>
      </AbsoluteFill>
    </AbsoluteFill>
  )
}
