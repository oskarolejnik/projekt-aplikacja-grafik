import { useEffect, useLayoutEffect } from 'react'
import Lenis from 'lenis'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import 'lenis/dist/lenis.css'

// Infrastruktura motion premium landingu „Lokalo Noir": Lenis (smooth-scroll) spięty
// z GSAP ScrollTrigger + zestaw hooków (reveal, parallax, sceny pinned). Wszystko
// bezwzględnie respektuje prefers-reduced-motion — wtedy zero Lenis, zero scrubu,
// treść statycznie widoczna (żadnego ukrywania). Sprzątanie kompletne (destroy/kill/ticker).

gsap.registerPlugin(ScrollTrigger, SplitText)

// Sceny, które ustawiają stan POCZĄTKOWY (ukrycie przed animacją), muszą to zrobić PRZED
// pierwszym malowaniem — inaczej flash złożonego stanu. Na kliencie useLayoutEffect, na
// serwerze (gdyby kiedyś SSR) fallback do useEffect.
const useIsoLayout = typeof window !== 'undefined' ? useLayoutEffect : useEffect

export const reducedMotion = () =>
  typeof window !== 'undefined' && !!window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Czy w ogóle animujemy (JS + brak reduced-motion). Wejścia ukrywamy TYLKO gdy true —
// inaczej strona jest statycznie widoczna (żadnego flash-of-hidden).
export const motionOn = () =>
  typeof window !== 'undefined' && 'IntersectionObserver' in window && !reducedMotion()

// Czy używać sekcji PINNED (scroll-storytelling). Tylko desktop z myszą i ≥1024px —
// na dotyku/mobile pin bywa janky (pasek adresu zmienia wysokość viewportu, dotyk klei się
// do przypiętej sceny), więc tam pokazujemy statyczny wariant sekcji.
export const canPin = () =>
  motionOn() && !!(window.matchMedia && window.matchMedia('(pointer: fine)').matches) && window.innerWidth >= 1024

// ── Globalny smooth-scroll (Lenis) spięty z tickerem GSAP i ScrollTrigger ──
// Zwraca cleanup. Native scroll przy reduced-motion. Kotwice #hash płyną przez Lenis.
export function useLenisGsap(enabled = true) {
  useEffect(() => {
    if (!enabled || reducedMotion() || typeof window === 'undefined') return

    // Na dotyku (mobile/tablet) NIE uruchamiamy Lenisa — natywne momentum iOS/Androida
    // jest lepsze niż smooth-scroll na wierzchu. ScrollTrigger (reveals) i tak działa na
    // natywnym scrollu; dla kotwic włączamy natywny scroll-behavior: smooth.
    const fine = window.matchMedia && window.matchMedia('(pointer: fine)').matches
    if (!fine) {
      const el = document.documentElement
      const prev = el.style.scrollBehavior
      el.style.scrollBehavior = 'smooth'
      const refreshM = () => ScrollTrigger.refresh()
      window.addEventListener('load', refreshM)
      const tm = window.setTimeout(refreshM, 400)
      return () => { el.style.scrollBehavior = prev; window.removeEventListener('load', refreshM); clearTimeout(tm) }
    }

    const lenis = new Lenis({
      duration: 1.05,
      // ease-out-expo: mocny, bez odbić (zgodnie z systemem ruchu)
      easing: (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      touchMultiplier: 1.4,
      wheelMultiplier: 1,
    })

    // Lenis napędza update ScrollTriggera; GSAP ticker napędza raf Lenisa (jeden zegar).
    lenis.on('scroll', ScrollTrigger.update)
    if (import.meta.env && import.meta.env.DEV) window.__lenis = lenis  // podgląd w QA (tylko dev)
    const onTick = (time) => lenis.raf(time * 1000)
    gsap.ticker.add(onTick)
    gsap.ticker.lagSmoothing(0)

    // Płynne przewijanie do kotwic w obrębie landingu (nagłówek ~72px offsetu).
    const onClick = (e) => {
      const a = e.target.closest && e.target.closest('a[href^="#"]')
      if (!a) return
      const href = a.getAttribute('href')
      if (!href || href.length < 2) return
      const cel = document.querySelector(href)
      if (cel) { e.preventDefault(); lenis.scrollTo(cel, { offset: -72 }) }
    }
    document.addEventListener('click', onClick)

    // Po doczytaniu fontów/obrazów pozycje triggerów mogą się zmienić → odśwież.
    const refresh = () => ScrollTrigger.refresh()
    window.addEventListener('load', refresh)
    let tid = 0
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => { tid = window.setTimeout(refresh, 60) })
    } else {
      tid = window.setTimeout(refresh, 500)
    }

    return () => {
      document.removeEventListener('click', onClick)
      window.removeEventListener('load', refresh)
      if (tid) clearTimeout(tid)
      gsap.ticker.remove(onTick)
      gsap.ticker.lagSmoothing(500, 33)
      lenis.destroy()
      // NIE zabijamy globalnie ScrollTriggerów — każdy hook (useReveal/useParallax/useGsapScene)
      // sprząta własne przez gsap.context().revert(). Lenis nie tworzy własnych triggerów.
      if (import.meta.env && import.meta.env.DEV) delete window.__lenis
    }
  }, [enabled])
}

// ── Reveal przy wejściu w kadr (apple-like) ──
// Obsługuje ZARÓWNO [data-animate] (="up|left|right|scale") JAK I stary [data-rv]
// (wariant z klas rv-l/rv-r/rv-scale) — dzięki temu sekcje Role/Platformy/WhiteLabel/
// Zaufanie/Cennik ożywają bez edycji każdego pliku. Po wejściu CZYŚCIMY inline transform
// (clearProps), żeby nie nadpisać CSS-owego tiltu kart (.tilt używa własnego transformu).
const REVEAL_SEL = '[data-animate], [data-rv]'
function _revealKind(el) {
  if (el.dataset.animate) return el.dataset.animate
  if (el.classList.contains('rv-l')) return 'left'
  if (el.classList.contains('rv-r')) return 'right'
  if (el.classList.contains('rv-scale')) return 'scale'
  return 'up'
}
export function useReveal(scopeRef, enabled = true) {
  useEffect(() => {
    if (!enabled || reducedMotion() || typeof window === 'undefined') return
    const scope = (scopeRef && scopeRef.current) || document.body
    const ctx = gsap.context(() => {
      const set = (el) => {
        const kind = _revealKind(el)
        const from = { opacity: 0, willChange: 'transform, opacity' }
        if (kind === 'up') from.y = 46
        else if (kind === 'left') from.x = -52
        else if (kind === 'right') from.x = 52
        else if (kind === 'scale') { from.y = 34; from.scale = 0.955 }
        gsap.set(el, from)
      }
      gsap.utils.toArray(REVEAL_SEL).forEach(set)
      ScrollTrigger.batch(REVEAL_SEL, {
        start: 'top 86%',
        onEnter: (batch) =>
          gsap.to(batch, {
            opacity: 1, x: 0, y: 0, scale: 1,
            duration: 0.9, ease: 'power3.out', stagger: 0.08, overwrite: true,
            // clearProps transform → oddajemy kontrolę CSS (tilt/hover) po odsłonięciu.
            onComplete: () => gsap.set(batch, { clearProps: 'transform,willChange' }),
          }),
      })
    }, scope)
    return () => ctx.revert()
  }, [scopeRef, enabled])
}

// ── Parallax warstwy: element płynie w osi Y względem scrolla (głębia) ──
// speed>0 = wolniej (w tył), speed<0 = szybciej (w przód). elRef → element.
export function useParallax(elRef, speed = 0.12, enabled = true) {
  useEffect(() => {
    if (!enabled || reducedMotion() || typeof window === 'undefined') return
    const el = elRef && elRef.current
    if (!el) return
    const ctx = gsap.context(() => {
      gsap.to(el, {
        yPercent: -speed * 100,
        ease: 'none',
        scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true },
      })
    })
    return () => ctx.revert()
  }, [elRef, speed, enabled])
}

// ── Dowolna scena GSAP w scope (pinned/scrub) z automatycznym sprzątaniem ──
// buildFn(gsap, ScrollTrigger) tworzy animacje; wywoływane w gsap.context(scope).
export function useGsapScene(scopeRef, buildFn, enabled = true) {
  // useLayoutEffect: stan początkowy (ukrycie) aplikuje się PRZED malowaniem → zero flashu.
  useIsoLayout(() => {
    if (!enabled || reducedMotion() || typeof window === 'undefined') return
    const scope = scopeRef && scopeRef.current
    if (!scope) return
    const ctx = gsap.context(() => buildFn(gsap, ScrollTrigger), scope)
    return () => ctx.revert()
  }, [scopeRef, enabled]) // eslint-disable-line react-hooks/exhaustive-deps
}

export { gsap, ScrollTrigger, SplitText }
