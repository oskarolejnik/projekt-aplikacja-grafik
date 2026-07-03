// Tokeny spotu = rejestry z DESIGN.md: scena „Lokalo Noir" (noc + złota nitka),
// ekrany produktu w języku „Cichej sceny" (mięta). Fonty jak w produkcie:
// Space Grotesk (display) + Inter (body) — ładowane oficjalną paczką Google Fonts.
import { loadFont as loadGrotesk } from '@remotion/google-fonts/SpaceGrotesk'
import { loadFont as loadInter } from '@remotion/google-fonts/Inter'

const grotesk = loadGrotesk('normal', { weights: ['500', '700'] })
const inter = loadInter('normal', { weights: ['400', '600', '700'] })

export const C = {
  // Scena noir (landing)
  noc: '#141312',
  wegiel: '#1C1A18',
  zloto: '#C9A96A',
  zloto2: '#E7CF9B',
  // Produkt „Cicha scena"
  bg: '#1C1C1E',
  surface: '#26262A',
  surface2: '#323236',
  line: 'rgba(255,255,255,0.08)',
  ink: '#F4F4F5',
  muted: '#A1A1AA',
  mint: '#9DC4B1',
  lemon: '#E8D9A8',
  blush: '#C9B6C1',
  coral: '#DFA9A2',
  cream: '#F4F4F5',
}

export const F = {
  display: grotesk.fontFamily,
  body: inter.fontFamily,
}

export const zl = (n: number) => Math.round(n).toLocaleString('pl-PL')
