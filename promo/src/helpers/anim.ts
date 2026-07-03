// Pomocnicy ruchu: premium easing (mocne expo-out, zero odbić), wejścia
// z kierunkowym „motion blur" (rozmycie proporcjonalne do prędkości wejścia).
import type { CSSProperties } from 'react'
import { Easing, interpolate } from 'remotion'

export const EXPO = Easing.bezier(0.16, 1, 0.3, 1)
export const SNAP = Easing.bezier(0.23, 1, 0.32, 1)
export const SMOOTH = Easing.bezier(0.77, 0, 0.175, 1)

// Postęp 0→1 od `start` przez `dur` klatek (clamp z obu stron).
export const en = (frame: number, start: number, dur = 18, easing = EXPO) =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  })

// Wartość liczbowa z easingiem (skróty do transformów).
export const lerp = (t: number, a: number, b: number) => a + (b - a) * t

type Kierunek = 'up' | 'down' | 'left' | 'right' | 'zoom'

// Styl wejścia elementu: przesunięcie + opacity + kierunkowe rozmycie ruchu.
export const wjazd = (
  frame: number,
  start: number,
  dur = 18,
  kierunek: Kierunek = 'up',
  dystans = 90,
): CSSProperties => {
  const t = en(frame, start, dur)
  const d = (1 - t) * dystans
  const blur = (1 - t) * 10
  const map: Record<Kierunek, string> = {
    up: `translateY(${d}px)`,
    down: `translateY(${-d}px)`,
    left: `translateX(${d}px)`,
    right: `translateX(${-d}px)`,
    zoom: `scale(${lerp(t, 0.86, 1)})`,
  }
  return {
    opacity: t,
    transform: map[kierunek],
    filter: blur > 0.4 ? `blur(${blur.toFixed(1)}px)` : undefined,
  }
}

// Wyjście sceny: szybki zoom + fade w ostatnich klatkach sekwencji.
export const wyjscie = (frame: number, dur: number, ile = 8): CSSProperties => {
  const t = en(frame, dur - ile, ile, SMOOTH)
  if (t <= 0) return {}
  return {
    opacity: 1 - t,
    transform: `scale(${lerp(t, 1, 1.06)})`,
    filter: `blur(${(t * 8).toFixed(1)}px)`,
  }
}

// „Kamera": powolny push-in / pan przez całą scenę (paralaksa tła vs pierwszy plan).
export const kamera = (
  frame: number,
  dur: number,
  odSkali = 1,
  doSkali = 1.06,
  panX = 0,
  panY = 0,
): CSSProperties => {
  const t = interpolate(frame, [0, dur], [0, 1], {
    extrapolateRight: 'clamp',
    easing: Easing.linear,
  })
  return {
    transform: `scale(${lerp(t, odSkali, doSkali)}) translate(${lerp(t, 0, panX)}px, ${lerp(t, 0, panY)}px)`,
  }
}
