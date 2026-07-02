// Ciemna karta z 1px translucentnym obrysem i dyskretnym cieniem (Cicha scena).
export function Card({ className = '', children, ...props }) {
  return (
    <div {...props} className={`card ${className}`}>
      {children}
    </div>
  )
}

// Nagłówek sekcji z opcjonalnym podtytułem i akcjami po prawej.
export function SectionHeader({ title, subtitle, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight text-ink">{title}</h2>
        {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </div>
  )
}
