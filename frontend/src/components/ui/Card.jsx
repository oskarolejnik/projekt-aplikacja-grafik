import { Hint } from './Hint'

// Ciemna karta z 1px translucentnym obrysem i dyskretnym cieniem (Cicha scena).
export function Card({ className = '', children, ...props }) {
  return (
    <div {...props} className={`card ${className}`}>
      {children}
    </div>
  )
}

// Nagłówek sekcji z akcjami po prawej. Tekst objaśniający (`subtitle` lub `hint`) chowamy pod „?"
// obok tytułu — schludniej, bez rozwlekłego akapitu w linii (klik na „?" odsłania opis).
// `subtitleInline` — wyjątek: gdy opis MA zostać widoczny w linii (rzadko), przekaż go tutaj.
export function SectionHeader({ title, subtitle, hint, subtitleInline, children }) {
  const pomoc = hint || subtitle
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h2 className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight text-ink">
          {title}
          {pomoc && <Hint>{pomoc}</Hint>}
        </h2>
        {subtitleInline && <p className="mt-1.5 text-sm text-muted">{subtitleInline}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </div>
  )
}
