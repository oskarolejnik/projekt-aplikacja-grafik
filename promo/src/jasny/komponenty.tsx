// Styl „jasny teaser" (referencja: app-promo à la dnyxstudios): biała scena
// z pastelowymi poświatami, pływające karty UI z WIELKIMI miękkimi cieniami,
// mocniejszy kierunkowy motion blur, narracja pisana wewnątrz elementów UI.
import type { CSSProperties, FC, ReactNode } from 'react'
import { AbsoluteFill } from 'remotion'
import { F } from '../theme'

// Paleta teasera na CZERNI (feedback: „wszystko na czarnym tle"). Jasne karty
// (powiadomienia, karteczka) świecą na czerni jak bannery iOS w trybie nocnym.
export const J = {
  tlo: '#0C0C0E',
  ink: '#17181C',        // tekst na jasnych kartach
  muted: '#6B6F76',      // tekst drugorzędny na jasnych kartach
  jasnyInk: '#F4F4F5',   // tekst na czerni
  jasnyMuted: '#9A9CA3',
  karta: '#FFFFFF',
  zolty: '#F5C84C',
}

// Cień „pływającej" karty + delikatna kreska światła (na czerni cień robi
// głębię tylko przy poświacie tła; kreska odcina kartę od tła).
export const CIEN = '0 30px 70px -18px rgba(0,0,0,0.7), 0 8px 24px -12px rgba(0,0,0,0.5)'

export const CiemnaScena: FC<{ children: ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: J.tlo }}>
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(820px 620px at 50% -4%, rgba(255,255,255,0.05), transparent 62%),
          radial-gradient(700px 520px at 88% 88%, rgba(150,170,255,0.05), transparent 62%),
          radial-gradient(640px 480px at 8% 70%, rgba(242,170,215,0.04), transparent 60%)
        `,
      }}
    />
    {children}
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(115% 100% at 50% 50%, transparent 66%, rgba(0,0,0,0.5) 100%)',
      }}
    />
  </AbsoluteFill>
)

// Powiadomienie push w stylu iOS (jasne, z ikonką-kaflem) — nośnik narracji.
export const Powiadomienie: FC<{
  ikona: ReactNode
  tytul: string
  tresc: string
  kiedy?: string
  w?: number
  style?: CSSProperties
}> = ({ ikona, tytul, tresc, kiedy = 'teraz', w = 660, style }) => (
  <div
    style={{
      width: w,
      display: 'flex',
      gap: 18,
      alignItems: 'center',
      background: 'rgba(255,255,255,0.9)',
      backdropFilter: 'blur(14px)',
      borderRadius: 26,
      padding: '20px 26px',
      boxShadow: CIEN,
      ...style,
    }}
  >
    <div
      style={{
        width: 62,
        height: 62,
        borderRadius: 16,
        overflow: 'hidden',
        flexShrink: 0,
        display: 'grid',
        placeItems: 'center',
      }}
    >
      {ikona}
    </div>
    <div style={{ minWidth: 0, flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
        <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 26, color: J.ink }}>{tytul}</span>
        <span style={{ fontFamily: F.body, fontSize: 19, color: J.muted, flexShrink: 0 }}>{kiedy}</span>
      </div>
      <div style={{ fontFamily: F.body, fontSize: 24, color: J.muted, marginTop: 2 }}>{tresc}</div>
    </div>
  </div>
)

// Kafelek-ikonka aplikacji do powiadomień (kolor + litera/glif).
export const IkonaApki: FC<{ kolor: string; glif: string; ciemnyGlif?: boolean }> = ({ kolor, glif, ciemnyGlif }) => (
  <div
    style={{
      width: '100%',
      height: '100%',
      background: kolor,
      display: 'grid',
      placeItems: 'center',
      fontFamily: F.display,
      fontWeight: 700,
      fontSize: 30,
      color: ciemnyGlif ? '#1C1C1E' : '#fff',
    }}
  >
    {glif}
  </div>
)

// Karteczka-notatka (żółty nagłówek jak w referencji) z listą zadań.
export const Karteczka: FC<{ data: string; tytul: string; zadania: string[]; w?: number; style?: CSSProperties }> = ({
  data,
  tytul,
  zadania,
  w = 560,
  style,
}) => (
  <div style={{ width: w, borderRadius: 26, overflow: 'hidden', boxShadow: CIEN, background: J.karta, ...style }}>
    <div
      style={{
        background: J.zolty,
        padding: '16px 26px',
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: F.body,
        fontWeight: 600,
        fontSize: 22,
        color: 'rgba(23,24,28,0.72)',
      }}
    >
      <span>{data}</span>
      <span>···</span>
    </div>
    <div style={{ padding: '24px 30px 30px' }}>
      <div style={{ fontFamily: F.body, fontWeight: 700, fontSize: 32, color: J.ink, borderBottom: '1.5px solid rgba(23,24,28,0.12)', paddingBottom: 12 }}>
        {tytul}
      </div>
      <div style={{ marginTop: 18, display: 'grid', gap: 14 }}>
        {zadania.map((z) => (
          <div key={z} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ width: 24, height: 24, borderRadius: 99, border: '2px solid rgba(23,24,28,0.3)', flexShrink: 0 }} />
            <span style={{ fontFamily: F.body, fontSize: 25, color: J.ink }}>{z}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
)
