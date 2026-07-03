// Sceny teasera 9:16 NA CZERNI, v3 (feedback: równe powiadomienia + więcej,
// czyste tło karteczki + dłuższa lista, nowe sceny: auto-grafik, dyspozycje,
// rozbudowany pulpit, telefon pracownika; wszystko równe i Apple-like).
// Język ruchu: slide-in OD BOKU (naprzemiennie prawy/lewy per scena),
// tytuły zawsze w tym samym miejscu (top 240, 56 px, wyśrodkowane).
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { en, kamera, lerp, wjazd, wyjscie, SMOOTH } from '../helpers/anim'
import { GrafikOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { GrafikAutoOkno, DyspozycjeOkno, PulpitProOkno, Telefon } from './okna2'
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

// Tytuł sceny — ZAWSZE ta sama pozycja i skala (równość, spokój, Apple-like).
const Tytul: FC<{ tekst: string; delay?: number; bok?: 'left' | 'right' }> = ({ tekst, delay = 28, bok = 'left' }) => {
  const frame = useCurrentFrame()
  return (
    <div style={{ position: 'absolute', left: 40, right: 40, top: 240, textAlign: 'center', ...wjazd(frame, delay, 20, bok, 120) }}>
      <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 56, color: J.jasnyInk, letterSpacing: '-0.02em' }}>
        {tekst}
      </span>
    </div>
  )
}

// ── J1 [0–4.5 s]: wieczór managera — RÓWNE powiadomienia z prawej ─────────────
const POWIADOMIENIA: { kolor: string; glif: string; ciemny?: boolean; tytul: string; tresc: string; kiedy: string }[] = [
  { kolor: '#1D6F42', glif: 'X', tytul: 'Excel', tresc: 'Skoroszyt GRAFIK_v7_OSTATECZNY jest zablokowany przez innego użytkownika', kiedy: '21:40' },
  { kolor: '#34C759', glif: 'A', tytul: 'Ania (sala)', tresc: 'Szefie, mogę się zamienić na sobotę? Kasia się zgadza', kiedy: '21:52' },
  { kolor: '#8E8E93', glif: 'K', tytul: 'Kasia (bar)', tresc: 'Szefie, jutro jednak nie dam rady przyjść', kiedy: '21:58' },
  { kolor: '#F5C84C', glif: 'W', ciemny: true, tytul: 'Kalendarz', tresc: 'Wesele 120 os. — potwierdzić menu i zadatek do piątku', kiedy: '22:05' },
]

export const J1Powiadomienia: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} panY={-16}>
      <CiemnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 30 }}>
          {POWIADOMIENIA.map((p, i) => (
            <div key={p.tytul} style={wjazd(frame, 6 + i * 20, 24, 'left', 340)}>
              <Powiadomienie
                ikona={<IkonaApki kolor={p.kolor} glif={p.glif} ciemnyGlif={p.ciemny} />}
                tytul={p.tytul}
                tresc={p.tresc}
                kiedy={p.kiedy}
                w={880}
              />
            </div>
          ))}
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J2 [4.5–8.5 s]: karteczka „Jutro:" z lewej — czyste tło, dłuższa lista ────
export const J2Karteczka: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.06} panY={-12}>
      <CiemnaScena>
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 4, 26, 'right', 380)}>
            <Karteczka
              data="pt, 3 lip"
              tytul="Jutro:"
              zadania={[
                'ułożyć grafik na tydzień',
                'policzyć godziny i wypłaty',
                'oddzwonić: wesele 120 os.',
                'sprawdzić utarg z wczoraj',
                'zebrać dyspozycyjność zespołu',
                'zamówić środki czystości',
                'potwierdzić rezerwacje na sobotę',
              ]}
              w={720}
            />
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J3 [8.5–12.5 s]: automatyzacja grafiku — „auto" wciska się, kaskada ───────
export const J3AutoGrafik: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <CiemnaScena>
        <Tytul tekst="Grafik układa się sam." delay={30} bok="left" />
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 2, 24, 'left', 420)}>
            <div style={{ transform: 'scale(1.08)' }}>
              <GrafikAutoOkno w={920} start={8} />
            </div>
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J4 [12.5–16 s]: dyspozycyjność — zespół zgłasza z telefonu ────────────────
export const J4Dyspozycje: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <CiemnaScena>
        <Tytul tekst="Zespół sam zgłasza dyspozycyjność." delay={26} bok="right" />
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 2, 24, 'right', 420)}>
            <div style={{ transform: 'scale(1.06)' }}>
              <DyspozycjeOkno w={720} start={10} />
            </div>
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J5 [16–21 s]: karuzela — rozbudowany pulpit właściciela + rezerwacje ──────
const EKRANY: { El: FC<{ w?: number; start?: number }>; w: number; skala: number; tytul: string; bok: 'lewy' | 'prawy' }[] = [
  { El: PulpitProOkno, w: 920, skala: 1.04, tytul: 'Właściciel widzi wszystko. Na żywo.', bok: 'prawy' },
  { El: RezerwacjaOkno, w: 700, skala: 1.18, tytul: 'Rezerwacje online. 0% prowizji.', bok: 'lewy' },
]
const SEGMENT = 75

export const J5Karuzela: FC<{ dur: number }> = ({ dur }) => {
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
                  top: 240,
                  textAlign: 'center',
                  transform: `translateX(${x * 0.55}px)`,
                  opacity: Math.min(en(frame, od + 12, 16), 1 - wyj),
                }}
              >
                <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 56, color: J.jasnyInk, letterSpacing: '-0.02em' }}>
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

// ── J6 [21–25 s]: pracownik ma wszystko na telefonie ──────────────────────────
export const J6Telefon: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.06} panY={-8}>
      <CiemnaScena>
        <Tytul tekst="Pracownik ma wszystko na telefonie." delay={26} bok="left" />
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', paddingTop: 120 }}>
          <div style={wjazd(frame, 2, 26, 'left', 420)}>
            <Telefon w={560} start={16} />
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J7 [25–28 s]: wypłaty co do minuty ────────────────────────────────────────
export const J7Wyplaty: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaJ dur={dur} odSkali={1.0} doSkali={1.05}>
      <CiemnaScena>
        <Tytul tekst="Wypłaty co do minuty." delay={24} bok="right" />
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={wjazd(frame, 2, 24, 'right', 420)}>
            <div style={{ transform: 'scale(1.22)' }}>
              <WyplataOkno w={680} start={8} />
            </div>
          </div>
        </AbsoluteFill>
      </CiemnaScena>
    </ScenaJ>
  )
}

// ── J8 [28–31 s]: puenta — białe boldy jak w keynote ──────────────────────────
export const J8Puenta: FC<{ dur: number }> = ({ dur }) => {
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

// ── J9 [31–34 s]: brand-reveal ────────────────────────────────────────────────
export const J9Brand: FC<{ dur: number }> = ({ dur }) => {
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
