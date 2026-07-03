// Syntezator ścieżki spotu — WŁASNA kompozycja generowana kodem (zero próbek
// i materiałów osób trzecich → pełne prawa, bezpieczna komercyjnie).
// Minimalny, głęboki puls 120 BPM pod noir-premium: kick + sub-bas z sidechainem,
// cichy hi-hat na offbeacie, szeroki pad. Zapis: promo/public/beat.wav.
// Użycie: node scripts/beat.js   (odtwarzalne — plik .wav nie wchodzi do repo)
const fs = require('fs')
const path = require('path')

const SR = 44100
const BPM = 120
const BEAT = 60 / BPM // 0.5 s
const DLUGOSC = 38 // s — pokrywa wszystkie spoty (25 s / 20 s / 34 s teaser)
const N = Math.round(SR * DLUGOSC)

const L = new Float64Array(N)
const R = new Float64Array(N)

const TAU = Math.PI * 2

// ── Kick: sweep 110→46 Hz, wykładniczy zanik ─────────────────────────────────
function kick(t0) {
  const dl = 0.26
  let faza = 0
  for (let i = 0; i < dl * SR; i++) {
    const t = i / SR
    const idx = Math.round(t0 * SR) + i
    if (idx >= N) break
    const f = 46 + 64 * Math.exp(-t / 0.045)
    faza += (TAU * f) / SR
    const amp = Math.exp(-t / 0.09) * 0.95
    const s = Math.sin(faza) * amp
    L[idx] += s
    R[idx] += s
  }
}

// ── Hi-hat: szum górnoprzepustowy (różniczka), krótki zanik ──────────────────
function hat(t0, dl = 0.035, gain = 0.11) {
  let prev = 0
  for (let i = 0; i < dl * SR; i++) {
    const idx = Math.round(t0 * SR) + i
    if (idx >= N) break
    const bialy = Math.random() * 2 - 1
    const hp = bialy - prev // prosta górnoprzepustowość
    prev = bialy
    const amp = Math.exp(-(i / SR) / (dl / 3)) * gain
    L[idx] += hp * amp * 0.8
    R[idx] += hp * amp * 1.0 // odrobinę szerzej w prawo
  }
}

// ── Sub-bas: A1 (55 Hz) ósemki z sidechainem po kicku ────────────────────────
function bas(t0, dl) {
  for (let i = 0; i < dl * SR; i++) {
    const t = i / SR
    const idx = Math.round(t0 * SR) + i
    if (idx >= N) break
    // pozycja względem ostatniego beatu → sidechain (bas oddycha pod kickiem)
    const wBeacie = ((t0 + t) % BEAT) / BEAT
    const sidechain = Math.min(1, wBeacie / 0.35)
    const obw = Math.min(1, (i / SR) / 0.008) * Math.exp(-t / (dl * 0.9))
    const s = Math.sin(TAU * 55 * (t0 + t)) * 0.34 * obw * sidechain
    L[idx] += s
    R[idx] += s
  }
}

// ── Pad: A2 + E3, wolne tremolo, szeroka stereofonia ─────────────────────────
for (let i = 0; i < N; i++) {
  const t = i / SR
  const trem = 0.75 + 0.25 * Math.sin(TAU * 0.25 * t)
  L[i] += Math.sin(TAU * 110 * t) * 0.05 * trem
  R[i] += Math.sin(TAU * 164.81 * t) * 0.05 * trem
}

// ── Aranżacja: groove przez cały czas; open-hat domyka każdy takt ────────────
const beatow = Math.floor(DLUGOSC / BEAT)
for (let b = 0; b < beatow; b++) {
  const t0 = b * BEAT
  kick(t0)
  hat(t0 + BEAT / 2) // offbeat
  if (b % 4 === 3) hat(t0 + BEAT / 2, 0.12, 0.09) // open-hat na końcu taktu
  bas(t0 + BEAT / 4, BEAT / 4) // ósemka „i"
  bas(t0 + (3 * BEAT) / 4, BEAT / 4) // ósemka „a"
}

// ── Master: fade-in, miękkie ograniczenie (tanh), 16-bit PCM ─────────────────
const out = Buffer.alloc(44 + N * 4)
out.write('RIFF', 0)
out.writeUInt32LE(36 + N * 4, 4)
out.write('WAVE', 8)
out.write('fmt ', 12)
out.writeUInt32LE(16, 16)
out.writeUInt16LE(1, 20) // PCM
out.writeUInt16LE(2, 22) // stereo
out.writeUInt32LE(SR, 24)
out.writeUInt32LE(SR * 4, 28)
out.writeUInt16LE(4, 32)
out.writeUInt16LE(16, 34)
out.write('data', 36)
out.writeUInt32LE(N * 4, 40)

for (let i = 0; i < N; i++) {
  const fadeIn = Math.min(1, i / (0.4 * SR))
  const l = Math.tanh(L[i] * 0.9) * fadeIn
  const r = Math.tanh(R[i] * 0.9) * fadeIn
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, l)) * 32767), 44 + i * 4)
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, r)) * 32767), 46 + i * 4)
}

const cel = path.join(__dirname, '..', 'public', 'beat.wav')
fs.mkdirSync(path.dirname(cel), { recursive: true })
fs.writeFileSync(cel, out)
console.log(`OK ${cel} (${(out.length / 1e6).toFixed(1)} MB, ${DLUGOSC} s @ ${BPM} BPM)`)
