import { useEffect } from 'react'

// Czy użytkownik prosi o ograniczony ruch — animacje wtedy wyłączamy/upraszczamy.
export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && !!window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Czy w ogóle animować wejścia: jest JS + IntersectionObserver + brak reduced-motion.
// Root dostaje data-anim="on" JUŻ w JSX (nie w efekcie) — inaczej treść mignęłaby widoczna
// przed pierwszym efektem. Gdy false → nic nie ukrywamy, strona jest statycznie widoczna.
export const animacjeWlaczone = () =>
  typeof window !== 'undefined' && 'IntersectionObserver' in window && !prefersReducedMotion()

// Reveal przy scrollu: elementy z [data-rv] dostają klasę .in, gdy wejdą w kadr (raz).
export function useReveal(rootRef) {
  useEffect(() => {
    const root = rootRef.current
    if (!root || !animacjeWlaczone()) return
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('in')
            io.unobserve(e.target)
          }
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.16 },
    )
    root.querySelectorAll('[data-rv]').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [rootRef])
}

// Natywny smooth-scroll dla kotwic w obrębie strony (a[href^="#"]) — wyłączony przy
// prefers-reduced-motion. Świadomie NIE przechwytujemy scrolla myszy/trackpada, żeby nie
// psuć natywnego momentum (to robi się dobrze tylko ze strojoną biblioteką typu Lenis).
export function useSmoothAnchors() {
  useEffect(() => {
    if (prefersReducedMotion()) return
    const el = document.documentElement
    const prev = el.style.scrollBehavior
    el.style.scrollBehavior = 'smooth'
    return () => {
      el.style.scrollBehavior = prev
    }
  }, [])
}
