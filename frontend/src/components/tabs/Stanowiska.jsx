import { useEffect, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm } from '../../lib/format'

// Karta stanowiska z edycją inline. Lokalny stan seedowany z propsów
// (klucz=id => świeży stan po przeładowaniu listy). Układ kartowy zamiast tabeli —
// nazwa ma pełną szerokość (czytelna na mobile), bez ucinania.
function StanowiskoRow({ s, i = 0, onChanged }) {
  const { toast, confirm } = useToast()
  const [nazwa, setNazwa] = useState(s.nazwa)
  const [weekend, setWeekend] = useState(s.tylko_weekend)
  const [wszyscy, setWszyscy] = useState(!!s.widoczny_dla_wszystkich)
  const [grupa, setGrupa] = useState(s.grupa_widocznosci || '')
  const [busy, setBusy] = useState(false)

  const zapisz = async () => {
    setBusy(true)
    try {
      await api(`/stanowiska/${s.id}`, 'PUT', {
        nazwa: nazwa.trim(), tylko_weekend: weekend,
        widoczny_dla_wszystkich: wszyscy, grupa_widocznosci: grupa.trim() || null,
      })
      toast('Zapisano zmiany.', 'success')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }
  const usun = async () => {
    if (!(await confirm(`Usunąć stanowisko „${s.nazwa}”?`))) return
    try {
      await api(`/stanowiska/${s.id}`, 'DELETE')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div className="animate-fade-up rounded-2xl border border-line bg-white/[0.02] p-4" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1.5">
          <span className="field-label">Nazwa stanowiska <span className="font-mono text-muted/60">#{s.id}</span></span>
          <input value={nazwa} onChange={(e) => setNazwa(e.target.value)} className="field" />
        </label>
        <label className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm font-medium text-ink">
          <input type="checkbox" checked={weekend} onChange={(e) => setWeekend(e.target.checked)} className="h-4 w-4 accent-mint" />
          Tylko weekend
        </label>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={zapisz} disabled={busy}>
            <Icon name="check" className="h-4 w-4" /> Zapisz
          </Button>
          <Button size="sm" variant="danger" onClick={usun} aria-label="Usuń stanowisko">
            <Icon name="trash" className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {/* Powiązania widoczności w „Moim grafiku" pracownika */}
      <div className="mt-3 flex flex-col gap-3 border-t border-line/60 pt-3 sm:flex-row sm:items-end">
        <label className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm font-medium text-ink">
          <input type="checkbox" checked={wszyscy} onChange={(e) => setWszyscy(e.target.checked)} className="h-4 w-4 accent-mint" />
          Widoczny dla wszystkich
        </label>
        <label className="flex flex-1 flex-col gap-1.5">
          <span className="field-label">Grupa widoczności</span>
          <input value={grupa} onChange={(e) => setGrupa(e.target.value)} placeholder="np. komp-wydawka" className="field" />
        </label>
      </div>
      <p className="mt-2 text-[11px] leading-snug text-muted/70">
        „Widoczny dla wszystkich" — każdy pracownik widzi, kto z tego stanowiska pracuje (np. Menadżer).
        „Grupa widoczności" — stanowiska z tą samą nazwą grupy widzą się wzajemnie (np. KOMP i Wydawka).
      </p>
    </div>
  )
}

export default function Stanowiska() {
  const { stanowiska, reloadDicts } = useData()
  const { toast } = useToast()
  const [nowa, setNowa] = useState('')
  const [nowaWeekend, setNowaWeekend] = useState(false)
  const [nowaWszyscy, setNowaWszyscy] = useState(false)
  const [nowaGrupa, setNowaGrupa] = useState('')
  const [pkStan, setPkStan] = useState('')
  const [pkNazwa, setPkNazwa] = useState('')
  const [pkOd, setPkOd] = useState('')

  useEffect(() => {
    reloadDicts()
  }, [reloadDicts])

  const dodajStanowisko = async () => {
    if (!nowa.trim()) return
    try {
      await api('/stanowiska', 'POST', {
        nazwa: nowa.trim(), tylko_weekend: nowaWeekend,
        widoczny_dla_wszystkich: nowaWszyscy, grupa_widocznosci: nowaGrupa.trim() || null,
      })
      setNowa('')
      setNowaWeekend(false)
      setNowaWszyscy(false)
      setNowaGrupa('')
      reloadDicts()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const dodajSzablon = async () => {
    if (!pkStan) {
      toast('Wybierz stanowisko.', 'error')
      return
    }
    if (!pkNazwa.trim()) {
      toast('Podaj nazwę rewiru.', 'error')
      return
    }
    try {
      await api(`/stanowiska/${pkStan}/podkategorie`, 'POST', { nazwa: pkNazwa.trim(), godz_od: pkOd ? `${pkOd}:00` : null })
      setPkNazwa('')
      setPkOd('')
      reloadDicts()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const usunSzablon = async (pid) => {
    try {
      await api(`/podkategorie/${pid}`, 'DELETE')
      reloadDicts()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const zSzablonami = stanowiska.filter((s) => s.podkategorie && s.podkategorie.length > 0)

  return (
    <div className="space-y-8">
      {/* Nowe stanowisko — wyśrodkowana kolumna */}
      <Card className="p-6 sm:p-8">
        <h3 className="mb-5 text-center font-display text-lg font-bold text-ink">Nowe stanowisko (kategoria główna)</h3>
        <div className="mx-auto flex max-w-md flex-col gap-4">
          <input
            value={nowa}
            onChange={(e) => setNowa(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && dodajStanowisko()}
            placeholder="Np. Sala, Bar…"
            className="field"
          />
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm font-medium text-ink">
            <input type="checkbox" checked={nowaWeekend} onChange={(e) => setNowaWeekend(e.target.checked)} className="h-4 w-4 accent-mint" />
            Tylko weekend
          </label>
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm font-medium text-ink">
            <input type="checkbox" checked={nowaWszyscy} onChange={(e) => setNowaWszyscy(e.target.checked)} className="h-4 w-4 accent-mint" />
            Widoczny dla wszystkich (np. Menadżer)
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Grupa widoczności (opcjonalnie)</span>
            <input value={nowaGrupa} onChange={(e) => setNowaGrupa(e.target.value)} placeholder="np. komp-wydawka — te same grupy widzą się wzajemnie" className="field" />
          </label>
          <Button onClick={dodajStanowisko} className="w-full">
            <Icon name="plus" className="h-4 w-4" /> Dodaj stanowisko
          </Button>
        </div>
      </Card>

      {/* Lista stanowisk — karty (nazwa pełnej szerokości, bez ucinania) */}
      <div className="space-y-3">
        {stanowiska.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted">Brak stanowisk. Dodaj pierwsze powyżej.</Card>
        ) : (
          stanowiska.map((s, i) => <StanowiskoRow key={s.id} s={s} i={i} onChanged={reloadDicts} />)
        )}
      </div>

      {/* Szablony rewirów / zmian */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Szablony rewirów / zmian" subtitle="Przypisz gotowe rewiry i godziny wejścia do istniejących stanowisk." />
        <div className="mx-auto mb-8 flex max-w-md flex-col gap-4 rounded-2xl border border-line bg-surface-2/60 p-5">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Stanowisko</span>
            <select value={pkStan} onChange={(e) => setPkStan(e.target.value)} className="field">
              <option value="" className="bg-surface">Wybierz…</option>
              {stanowiska.map((s) => (
                <option key={s.id} value={s.id} className="bg-surface text-ink">{s.nazwa}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Nazwa rewiru</span>
            <input value={pkNazwa} onChange={(e) => setPkNazwa(e.target.value)} placeholder="Wpisz rewir…" className="field" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Godzina wejścia</span>
            <input type="time" value={pkOd} onChange={(e) => setPkOd(e.target.value)} className="field" />
          </label>
          <Button variant="accent" onClick={dodajSzablon} className="w-full">
            <Icon name="plus" className="h-4 w-4" /> Dodaj szablon
          </Button>
        </div>

        {zSzablonami.length === 0 ? (
          <p className="text-center text-sm text-muted">Brak zdefiniowanych szablonów rewirów.</p>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {zSzablonami.map((s) => (
              <div key={s.id} className="rounded-2xl border border-line bg-surface-2/60 p-5">
                <h4 className="mb-4 flex items-center gap-2 border-b border-line pb-3 font-bold text-mint">
                  <Icon name="pin" className="h-4 w-4" /> {s.nazwa}
                </h4>
                <div className="space-y-3">
                  {s.podkategorie.map((pk) => (
                    <div key={pk.id} className="flex items-center justify-between rounded-xl border border-line bg-white/[0.03] p-3">
                      <div>
                        <div className="text-sm font-bold text-ink">{pk.nazwa}</div>
                        <div className="mt-0.5 flex items-center gap-1 font-mono text-xs text-muted">
                          <Icon name="clock" className="h-3 w-3" /> Wejście: {pk.godz_od ? hhmm(pk.godz_od) : 'Dowolnie'}
                        </div>
                      </div>
                      <button
                        onClick={() => usunSzablon(pk.id)}
                        className="rounded-lg border border-danger/20 bg-danger/10 p-2 text-danger transition hover:bg-danger/20"
                        aria-label="Usuń szablon"
                      >
                        <Icon name="trash" className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
