import { DOKUMENTY, WERSJA, AKTUALIZACJA, KONTAKT_RODO } from '../lib/legalne'

// Publiczna strona dokumentu prawnego (?polityka / ?regulamin). Treść z lib/legalne.js (swappable).
// Baner „wersja robocza" — do czasu akceptacji finalnej treści przez prawnika.
export default function Dokument({ ktory = 'polityka' }) {
  const doc = DOKUMENTY[ktory] || DOKUMENTY.polityka

  return (
    <div className="min-h-dvh bg-bg text-ink">
      <header className="border-b border-white/[0.06]">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-4 sm:px-6">
          <a href="/?produkt" className="font-brand text-lg font-bold text-ink">Lokalo</a>
          <a href="/?produkt" className="text-xs font-semibold text-muted transition hover:text-ink">← Strona główna</a>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
        <div className="mb-6 rounded-xl border border-lemon/30 bg-lemon/[0.08] px-4 py-3 text-xs text-lemon">
          Wersja robocza — treść w finalizacji prawnej. Wiążąca będzie wersja zaakceptowana przez radcę prawnego.
        </div>

        <h1 className="font-display text-3xl font-bold text-ink">{doc.tytul}</h1>
        <p className="mt-1 text-xs text-muted">Wersja {WERSJA} · aktualizacja {AKTUALIZACJA}</p>
        {doc.wstep && <p className="mt-4 text-sm leading-relaxed text-muted">{doc.wstep}</p>}

        <div className="mt-8 space-y-6">
          {doc.sekcje.map((s) => (
            <section key={s.h}>
              <h2 className="font-display text-base font-bold text-ink">{s.h}</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{s.t}</p>
            </section>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/[0.06] pt-5 text-xs text-muted">
          <a href="/?polityka" className="font-semibold text-mint hover:underline">Polityka prywatności</a>
          <a href="/?regulamin" className="font-semibold text-mint hover:underline">Regulamin</a>
          <a href={`mailto:${KONTAKT_RODO}`} className="hover:text-ink">{KONTAKT_RODO}</a>
        </div>
      </main>
    </div>
  )
}
