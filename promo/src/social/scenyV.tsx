// Sceny wersji PIONOWEJ 9:16 — tempo spokojne (feedback: „za szybki, zbyt
// agresywny"): jeden język ruchu = pojaw (fade + scale na miejscu), zero
// błysków i slamów, cennik jako KOLUMNA trzech w pełni widocznych kart.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion'
import { en, lerp, pojaw, SMOOTH } from '../helpers/anim'
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

const PodpisV: FC<{ tekst: string; delay?: number }> = ({ tekst, delay = 40 }) => {
  const frame = useCurrentFrame()
  return (
    <div style={{ ...pojaw(frame, delay, 18, 0.99), textAlign: 'center' }}>
      <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 34, color: C.muted }}>{tekst}</span>
    </div>
  )
}

// ── [0–3.7 s] Otwarcie: trzy bóle pojawiają się spokojnie → logo → obietnica ──
export const V1Hook: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaV dur={dur}>
      {/* Trzy znajome bóle — każdy ma czas wybrzmieć */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 30 }}>
        <Slam text="Excel." size={150} delay={0} out={56} />
        <Slam text="Papier." size={150} delay={14} out={56} color={C.muted} />
        <Slam text="Pięć apek." size={150} delay={28} out={56} />
      </AbsoluteFill>
      {/* Rozwiązanie */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 44 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 30, ...pojaw(frame, 64, 24) }}>
          <LogoMark size={170} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 120, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <Slam text="Jeden system." size={104} delay={84} color={C.zloto2} />
      </AbsoluteFill>
    </ScenaV>
  )
}

// ── [3.7–6.7 s] GRAFIK ────────────────────────────────────────────────────────
export const V2Grafik: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 64 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Grafik układa" size={104} delay={4} stagger={4} />
        <Kinetic text="się sam." size={104} delay={14} stagger={4} color={C.zloto2} />
      </div>
      <div style={pojaw(useCurrentFrame(), 10, 26)}>
        <Powieksz skala={1.12}>
          <GrafikOkno w={920} start={18} />
        </Powieksz>
      </div>
      <PodpisV tekst="dyspozycyjność → obsada → publikacja" delay={44} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [6.7–9.5 s] WYPŁATY ───────────────────────────────────────────────────────
export const V3Wyplaty: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 60 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Wypłaty" size={104} delay={4} stagger={4} />
        <Kinetic text="co do minuty." size={104} delay={12} stagger={4} color={C.zloto2} />
      </div>
      <div style={pojaw(useCurrentFrame(), 10, 26)}>
        <Powieksz skala={1.35}>
          <WyplataOkno w={640} start={14} />
        </Powieksz>
      </div>
      <PodpisV tekst="RCP → godziny → kwota · portfel na żywo" delay={44} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [9.5–12.3 s] REZERWACJE ───────────────────────────────────────────────────
export const V4Rezerwacje: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 56 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Rezerwacje online." size={96} delay={4} stagger={4} />
        <Kinetic text="0% prowizji." size={110} delay={14} stagger={4} color={C.zloto2} />
      </div>
      <div style={pojaw(useCurrentFrame(), 10, 26)}>
        <Powieksz skala={1.3}>
          <RezerwacjaOkno w={660} start={14} />
        </Powieksz>
      </div>
      <PodpisV tekst="widget na Twojej stronie · SMS + e-mail" delay={46} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [12.3–15 s] PULPIT ────────────────────────────────────────────────────────
export const V5Pulpit: FC<{ dur: number }> = ({ dur }) => (
  <ScenaV dur={dur}>
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 64 }}>
      <div style={{ textAlign: 'center' }}>
        <Kinetic text="Cały lokal" size={104} delay={4} stagger={4} />
        <Kinetic text="w liczbach. Na żywo." size={92} delay={12} stagger={4} color={C.zloto2} />
      </div>
      <div style={pojaw(useCurrentFrame(), 10, 26)}>
        <Powieksz skala={1.14}>
          <PulpitOkno w={900} start={14} />
        </Powieksz>
      </div>
      <PodpisV tekst="przychód · ruch · koszt pracy · alerty" delay={44} />
    </AbsoluteFill>
  </ScenaV>
)

// ── [15–18 s] CENNIK: kolumna trzech kart — wszystkie w pełni widoczne ────────
const PLANY_V = [
  { naz: 'Basic', cena: 99, opis: '1 lokal, bez limitu osób' },
  { naz: 'Pro', cena: 199, opis: 'Standard dla restauracji', flagowy: true },
  { naz: 'Premium', cena: 349, opis: 'Domy weselne i eventowe' },
]

const KartaV: FC<{ k: (typeof PLANY_V)[number]; i: number }> = ({ k, i }) => {
  const frame = useCurrentFrame()
  const start = 12 + i * 9
  const t = en(frame, start, 22)
  const flag = !!k.flagowy
  return (
    <div
      style={{
        width: 880,
        borderRadius: 32,
        border: `2px solid ${flag ? 'rgba(201,169,106,0.5)' : C.line}`,
        background: flag ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.03)',
        padding: '30px 44px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 20,
        opacity: t,
        transform: `scale(${lerp(t, 0.95, flag ? 1.03 : 1)})`,
        boxShadow: '0 30px 80px -30px rgba(0,0,0,0.8)',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 42, color: C.ink }}>{k.naz}</span>
          {flag && (
            <span
              style={{
                background: C.zloto,
                color: C.noc,
                fontFamily: F.body,
                fontWeight: 700,
                fontSize: 21,
                padding: '7px 18px',
                borderRadius: 99,
                whiteSpace: 'nowrap',
                opacity: en(frame, start + 14, 12),
              }}
            >
              Najczęściej wybierany
            </span>
          )}
        </div>
        <div style={{ fontFamily: F.body, fontSize: 25, color: C.muted, marginTop: 4 }}>{k.opis}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexShrink: 0 }}>
        <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 76, color: flag ? C.zloto2 : C.ink, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
          <Licznik do_={k.cena} start={start + 6} dur={26} />
        </span>
        <span style={{ fontFamily: F.body, fontSize: 26, color: C.muted }}>zł/mc</span>
      </div>
    </div>
  )
}

const TRUST_V = ['25+ modułów', '500+ testów', '0% prowizji']

export const V6Cennik: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <ScenaV dur={dur}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 46 }}>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zacznij za darmo." size={92} delay={0} stagger={4} />
          <Kinetic text="Rośnij, kiedy chcesz." size={72} delay={10} stagger={4} color={C.muted} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, alignItems: 'center' }}>
          {PLANY_V.map((k, i) => (
            <KartaV key={k.naz} k={k} i={i} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 34, alignItems: 'center' }}>
          {TRUST_V.map((t, i) => (
            <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 34, ...pojaw(frame, 52 + i * 8, 16, 0.98) }}>
              {i > 0 && <span style={{ color: C.zloto, fontSize: 30 }}>·</span>}
              <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 36, color: C.ink }}>{t}</span>
            </span>
          ))}
        </div>
      </AbsoluteFill>
    </ScenaV>
  )
}

// ── [18–20 s] CTA ─────────────────────────────────────────────────────────────
export const V7Cta: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  const sheen = interpolate(frame, [36, 54], [-140, 560], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: SMOOTH })
  return (
    <ScenaV dur={dur}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', gap: 52 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 26, ...pojaw(frame, 0, 22) }}>
          <LogoMark size={150} />
          <span style={{ fontFamily: F.display, fontWeight: 700, fontSize: 100, color: C.ink, letterSpacing: '-0.03em' }}>Lokalo</span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Kinetic text="Zbuduj przewagę" size={92} delay={12} stagger={4} />
          <Kinetic text="swojego lokalu." size={92} delay={22} stagger={4} color={C.zloto2} />
        </div>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 26,
            background: C.zloto,
            padding: '30px 92px',
            ...pojaw(frame, 30, 18, 0.96),
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
              background: 'linear-gradient(105deg, transparent, rgba(255,255,255,0.5), transparent)',
              transform: 'skewX(-18deg)',
            }}
          />
        </div>
        <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 30, color: C.muted, opacity: en(frame, 42, 14) }}>
          plan darmowy · bez karty · 5 minut
        </span>
      </AbsoluteFill>
    </ScenaV>
  )
}
