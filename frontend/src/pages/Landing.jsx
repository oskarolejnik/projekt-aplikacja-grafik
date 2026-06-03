import { Icon } from '../lib/icons'

const NAV = ['Home', 'About', 'Gallery', 'Event', 'Contact']

// Wizualizacja hero: sylwetka z „chmurką” zamiast głowy + orbitujące linie.
// W całości SVG (brak zewnętrznych zasobów — działa offline w Electronie).
function OrbitalVisual() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[460px]">
      {/* Miękka poświata za postacią */}
      <div aria-hidden className="absolute inset-10 rounded-full bg-page-glow opacity-20 blur-3xl" />

      {/* Orbity (powolny obrót, respektuje reduced-motion globalnie) */}
      <svg viewBox="0 0 400 400" className="absolute inset-0 h-full w-full animate-spin-orbit [transform-origin:center]" aria-hidden="true">
        <defs>
          <linearGradient id="orbit" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#F2B8CB" />
            <stop offset="50%" stopColor="#F2A2A2" />
            <stop offset="100%" stopColor="#F4E2A0" />
          </linearGradient>
        </defs>
        <g fill="none" stroke="url(#orbit)" strokeWidth="1.4" opacity="0.85">
          <ellipse cx="200" cy="200" rx="192" ry="118" transform="rotate(18 200 200)" />
          <ellipse cx="200" cy="200" rx="150" ry="186" transform="rotate(-28 200 200)" />
          <ellipse cx="200" cy="200" rx="176" ry="150" transform="rotate(64 200 200)" />
        </g>
        <circle cx="392" cy="178" r="5" fill="#F2A2A2" />
        <circle cx="24" cy="206" r="4" fill="#F4E2A0" />
        <circle cx="300" cy="372" r="3.5" fill="#A7D7C5" />
      </svg>

      {/* Postać w skali szarości */}
      <svg viewBox="0 0 400 400" className="absolute inset-0 h-full w-full" aria-hidden="true">
        <defs>
          <linearGradient id="body" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#9a9a9e" />
            <stop offset="100%" stopColor="#2f2f32" />
          </linearGradient>
          <linearGradient id="cloud" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="100%" stopColor="#D8D8D6" />
          </linearGradient>
        </defs>
        {/* Tułów / sukienka */}
        <path d="M150 400 C150 320 132 268 178 232 L222 232 C268 268 250 320 250 400 Z" fill="url(#body)" />
        {/* Ramiona */}
        <path d="M178 240 C150 250 138 300 150 360 L168 356 C160 312 168 270 192 256 Z" fill="url(#body)" opacity="0.92" />
        <path d="M222 240 C250 250 262 300 250 360 L232 356 C240 312 232 270 208 256 Z" fill="url(#body)" opacity="0.92" />
        {/* Szyja */}
        <rect x="188" y="196" width="24" height="44" rx="11" fill="#7c7c80" />
      </svg>

      {/* Chmurka jako „głowa” */}
      <svg viewBox="0 0 400 400" className="absolute inset-0 h-full w-full animate-float" aria-hidden="true">
        <g fill="url(#cloud)">
          <circle cx="200" cy="150" r="46" />
          <circle cx="158" cy="166" r="34" />
          <circle cx="242" cy="166" r="36" />
          <circle cx="180" cy="120" r="30" />
          <circle cx="224" cy="124" r="28" />
          <circle cx="200" cy="186" r="30" />
        </g>
        {/* Pastelowe akcenty wokół chmurki */}
        <circle cx="150" cy="120" r="6" fill="#F2B8CB" />
        <circle cx="258" cy="132" r="5" fill="#A7D7C5" />
        <path d="M250 96 l10 4 -10 4 z" fill="#F4E2A0" />
      </svg>
    </div>
  )
}

function Social({ name, d }) {
  return (
    <a href="#" aria-label={name} className="grid h-9 w-9 place-items-center rounded-full border border-white/10 text-muted transition hover:border-white/30 hover:text-ink">
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
        <path d={d} />
      </svg>
    </a>
  )
}

export default function Landing({ onEnter }) {
  return (
    <div className="min-h-dvh w-full bg-gradient-to-br from-[#bfe3cd] via-[#f4e7c6] to-[#f1c2d2] p-3 sm:p-6 md:p-10">
      <div className="relative mx-auto max-w-7xl overflow-hidden rounded-[1.75rem] border border-white/5 bg-bg shadow-2xl">
        {/* Wewnętrzne poświaty */}
        <div aria-hidden className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-page-glow opacity-[0.12] blur-3xl" />

        {/* Pasek nawigacji */}
        <header className="relative z-10 flex items-center justify-between px-6 py-6 md:px-10">
          <div className="flex items-center gap-10">
            <div className="grid h-10 w-10 place-items-center rounded-full border border-white/15 text-ink">
              <Icon name="sparkles" className="h-5 w-5" />
            </div>
            <nav className="hidden items-center gap-8 lg:flex">
              {NAV.map((item, i) => (
                <a
                  key={item}
                  href="#"
                  className={`text-xs font-semibold uppercase tracking-[0.15em] transition ${i === 0 ? 'text-ink' : 'text-muted hover:text-ink'}`}
                >
                  {item}
                </a>
              ))}
            </nav>
          </div>
          <button
            onClick={onEnter}
            className="rounded-lg border border-white/15 px-5 py-2 text-xs font-semibold uppercase tracking-[0.15em] text-ink transition hover:bg-white/5"
          >
            Login
          </button>
        </header>

        {/* Hero */}
        <div className="relative z-10 grid grid-cols-1 items-center gap-8 px-6 pb-14 pt-6 md:px-10 lg:grid-cols-2 lg:gap-6 lg:pb-20">
          {/* Lewa: tekst */}
          <div className="order-2 lg:order-1">
            <h1 className="font-display text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl xl:text-7xl">
              <span className="text-gradient">Creativity</span>
              <br />
              <span className="text-gradient">never ends</span>
            </h1>
            <p className="mt-6 max-w-md text-sm leading-relaxed text-muted">
              Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
            </p>
            <div className="mt-9 flex items-center gap-5">
              <button
                onClick={onEnter}
                className="rounded-full bg-cream px-9 py-3.5 text-sm font-bold uppercase tracking-[0.15em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98]"
              >
                Tickets
              </button>
              <button
                onClick={onEnter}
                className="rounded-full border border-white/20 px-7 py-3.5 text-sm font-semibold uppercase tracking-[0.15em] text-ink transition hover:bg-white/5"
              >
                Wejdź do panelu
              </button>
            </div>

            {/* Social */}
            <div className="mt-12 flex items-center gap-3">
              <Social name="Twitter" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
              <Social name="Facebook" d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
              <Social name="Instagram" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.332.014 7.052.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z" />
            </div>
          </div>

          {/* Prawa: wizual + data + FAB */}
          <div className="relative order-1 lg:order-2">
            <OrbitalVisual />

            {/* Data wydarzenia */}
            <div className="absolute bottom-2 right-2 text-right md:bottom-6 md:right-2">
              <div className="font-display text-4xl font-bold leading-none text-ink md:text-5xl">10</div>
              <div className="mt-1 text-sm font-medium uppercase tracking-[0.2em] text-muted">October 2023</div>
            </div>

            {/* Pływający przycisk „+” (akcent z referencji) */}
            <button
              onClick={onEnter}
              aria-label="Wejdź do aplikacji"
              className="absolute -bottom-4 left-1/2 grid h-12 w-12 -translate-x-1/2 place-items-center rounded-full bg-coral text-bg shadow-cta transition hover:brightness-105 active:scale-95 lg:left-auto lg:right-1/2"
            >
              <Icon name="plus" className="h-6 w-6" strokeWidth={2.5} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
