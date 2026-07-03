// Sceny wersji PIONOWEJ 9:16 (social-native): układy w pionie, UI powiększone
// pod kciuk, napisy NAD oknem (strefa bezpieczna od nakładek TikToka/Reels),
// każdy beat co ~0,5–1 s. Okna reużyte z wersji kinowej przez skalę.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion'
import { en, lerp, wjazd, SMOOTH } from '../helpers/anim'
import { GrafikOkno, PulpitOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { Kinetic } from '../components/Kinetic'
import { Licznik } from '../components/Licznik'
import { LogoMark } from '../components/LogoMark'
import { Slam } from '../components/Slam'
import { C, F } from '../theme'
import { ScenaV } from './ScenaV'

// Powiększenie okna produktu pod mały ekran (transform = tekst zostaje wektorowy).
const Powieksz: FC<{ skala: number; children: ReactNode }> = ({ skala, children }) => (
  <div style={{ transform: `scale(${skala})`, transformOrigin: 'center' }}>{children}</div>
)

// Duży podpis pod sceną (mniejszy „kicker" nad oknem robi Kinetic).
const PodpisV: FC<{ tekst: string; delay?: number }> = ({ tekst, delay = 26 }) => {
  const frame = useCurrentFrame()
  return (
    <div style={{ ...wjazd(frame, delay, 12, 'up', 34), textAlign: 'center' }}>
      <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 34, color: C.muted }}>{tekst}</span>
    </div>
  )
}

// ── [0–1.8 s] HOOK: ból w 3 ciosach → logo → obietnica ────────────────────────
export const V1Hook: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const logo = en(frame, 30, 10)
  return (
    <ScenaV dur={dur} odSkali={1} doSkali={1.07} panY={-16}>
      {/* Trzy ciosy bólu — na ekranie już w 1. klatce ruchu */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 26 }}>
        <Slam text="Excel." size={170} delay={0} out={27} />
        <Slam text="Papier." size={170} delay={8} out={27} color={C.muted} />
        <Slam text="Pięć apek." size={170} delay={16} out={27} />
      </AbsoluteFill>
      {/* Rozwiązanie: logo + złota obietnica */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 40 }}>
        <div
          style={{
            transform: `scale(${lerp(logo, 1.5, 1)})`,
            opacity: logo,
            filter: logo < 0.85 ? `blur(${((1 - logo) * 10).toFixed(1)}px)` : undefined,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 30,
          }}
        >
          <LogoMark size={170} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 120, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <Slam text="Jeden system." size={110} delay={38} color={C.zloto2} />
      </AbsoluteFill>
    </ScenaV>
  )
}

// ── [1.8–4.2 s] GRAFIK: okno na pełną szerokość, kaskada pigułek ──────────────
export const V2Grafik: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur} panY={-34}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 64 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Grafik układa" size={104} delay={0} stagger={2} dur={12} />
        <Kinetic text="się sam." size={104} delay={5} stagger={2} dur={12} color={C.zloto2} />
      </div>
      <div style={wjazd(useCurrentFrame(), 4, 14, 'up', 220)}>
        <Powieksz skala={1.12}>
          <GrafikOkno w={920} start={6} />
        </Powieksz>
      </div>
      <PodpisV tekst="dyspozycyjność → obsada → publikacja" delay={22} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [4.2–6.3 s] WYPŁATY: wielki licznik godzin i kwoty ────────────────────────
export const V3Wyplaty: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur} panY={-30}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 60 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Wypłaty" size={104} delay={0} stagger={2} dur={12} />
        <Kinetic text="co do minuty." size={104} delay={4} stagger={2} dur={12} color={C.zloto2} />
      </div>
      <div style={wjazd(useCurrentFrame(), 4, 14, 'up', 220)}>
        <Powieksz skala={1.35}>
          <WyplataOkno w={640} start={4} />
        </Powieksz>
      </div>
      <PodpisV tekst="RCP → godziny → kwota · portfel na żywo" delay={22} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [6.3–8.5 s] REZERWACJE: interfejs sam się klika, 0% prowizji ──────────────
export const V4Rezerwacje: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur} panY={-30}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 56 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Rezerwacje online." size={96} delay={0} stagger={2} dur={12} />
        <Kinetic text="0% prowizji." size={110} delay={5} stagger={2} dur={12} color={C.zloto2} />
      </div>
      <div style={wjazd(useCurrentFrame(), 4, 14, 'up', 220)}>
        <Powieksz skala={1.3}>
          <RezerwacjaOkno w={660} start={4} />
        </Powieksz>
      </div>
      <PodpisV tekst="widget na Twojej stronie · SMS + e-mail" delay={24} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [8.5–10.7 s] PULPIT: liczby na żywo ───────────────────────────────────────
export const V5Pulpit: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur} panY={-34}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 64 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Cały lokal" size={104} delay={0} stagger={2} dur={12} />
        <Kinetic text="w liczbach. Na żywo." size={96} delay={4} stagger={2} dur={12} color={C.zloto2} />
      </div>
      <div style={wjazd(useCurrentFrame(), 4, 14, 'up', 220)}>
        <Powieksz skala={1.14}>
          <PulpitOkno w={900} start={4} />
        </Powieksz>
      </div>
      <PodpisV tekst="przychód · ruch · koszt pracy · alerty kasowe" delay={22} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [10.7–13 s] CENNIK: talia kart, Pro na wierzchu + pas zaufania ────────────
const TALIA = [
  { naz: 'Basic', cena: 99, rot: -10, x: -300, y: 84 },
  { naz: 'Premium', cena: 349, rot: 10, x: 300, y: 84 },
  { naz: 'Pro', cena: 199, rot: 0, x: 0, y: 0, flagowy: true },
]

const KartaV: FC<{ k: (typeof TALIA)[number]; i: number }> = ({ k, i }) => {
  const frame = useCurrentFrame()
  const t = en(frame, 4 + i * 5, 14)
  const flag = !!k.flagowy
  return (
    <div
      style={{
        position: 'absolute',
        width: 560,
        borderRadius: 36,
        border: `2px solid ${flag ? 'rgba(201,169,106,0.5)' : C.line}`,
        background: flag ? '#242019' : '#1E1C1A',
        padding: '40px 46px',
        left: '50%',
        top: '50%',
        transform: `translate(-50%, -50%) translate(${k.x}px, ${lerp(t, k.y + 340, k.y)}px) rotate(${k.rot * t}deg) scale(${flag ? lerp(t, 0.9, 1.06) : 1})`,
        opacity: t,
        boxShadow: '0 50px 120px -40px rgba(0,0,0,0.9)',
        textAlign: 'center',
      }}
    >
      {flag && (
        <span
          style={{
            position: 'absolute',
            top: -24,
            left: '50%',
            transform: 'translateX(-50%)',
            background: C.zloto,
            color: C.noc,
            fontFamily: F.body,
            fontWeight: 700,
            fontSize: 24,
            padding: '10px 28px',
            borderRadius: 99,
            whiteSpace: 'nowrap',
            opacity: en(frame, 16, 8),
          }}
        >
          Najczęściej wybierany
        </span>
      )}
      <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 40, color: C.ink }}>{k.naz}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 10, marginTop: 14 }}>
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 108, color: C.ink, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
          <Licznik do_={k.cena} start={8 + i * 5} dur={18} />
        </span>
        <span style={{ fontFamily: F.body, fontSize: 28, color: C.muted }}>zł/mc</span>
      </div>
    </div>
  )
}

const TRUST_V = ['25+ modułów', '500+ testów', '0% prowizji']

export const V6Cennik: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaV dur={dur} panY={-24}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-start', paddingTop: 240 }}>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zacznij za darmo." size={96} delay={0} stagger={2} dur={12} />
          <Kinetic text="Rośnij, kiedy chcesz." size={76} delay={5} stagger={2} dur={12} color={C.muted} />
        </div>
      </AbsoluteFill>
      {/* Talia kart: boczne wjeżdżają pierwsze, Pro dobija na wierzch */}
      <AbsoluteFill style={{ top: -60 }}>
        {TALIA.map((k, i) => (
          <KartaV key={k.naz} k={k} i={i} />
        ))}
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-end', paddingBottom: 330 }}>
        <div style={{ display: 'flex', gap: 34, alignItems: 'center' }}>
          {TRUST_V.map((t, i) => (
            <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 34, ...wjazd(frame, 28 + i * 6, 12, 'up', 40) }}>
              {i > 0 && <span style={{ color: C.zloto, fontSize: 30 }}>·</span>}
              <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 36, color: C.ink }}>{t}</span>
            </span>
          ))}
        </div>
      </AbsoluteFill>
    </ScenaV>
  )
}

// ── [13–15 s] CTA: bezpośrednie, z pulsem i sheenem ───────────────────────────
export const V7Cta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const logo = en(frame, 0, 12)
  const cta = en(frame, 18, 10)
  const sheen = interpolate(frame, [24, 40], [-140, 560], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: SMOOTH })
  // Puls przycisku po wejściu — „kliknij mnie" bez krzyku
  const puls = 1 + Math.sin(Math.max(0, frame - 30) / 6) * 0.014
  return (
    <ScenaV dur={dur} odSkali={1} doSkali={1.06} panY={-12}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 52 }}>
        <div
          style={{
            transform: `scale(${lerp(logo, 1.4, 1)})`,
            opacity: logo,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 26,
          }}
        >
          <LogoMark size={150} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 100, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zbuduj przewagę" size={92} delay={8} stagger={2} dur={12} />
          <Kinetic text="swojego lokalu." size={92} delay={13} stagger={2} dur={12} color={C.zloto2} />
        </div>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 26,
            background: C.zloto,
            padding: '30px 92px',
            transform: `translateY(${lerp(cta, 70, 0)}px) scale(${puls})`,
            opacity: cta,
          }}
        >
          <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 44, color: C.noc }}>Zacznij za darmo</span>
          <span
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              width: 110,
              left: sheen,
              background: 'linear-gradient(105deg, transparent, rgba(255,255,255,0.6), transparent)',
              transform: 'skewX(-18deg)',
            }}
          />
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.muted, opacity: en(frame, 28, 10) }}>
          plan darmowy · bez karty · 5 minut
        </span>
      </AbsoluteFill>
    </ScenaV>
  )
}
