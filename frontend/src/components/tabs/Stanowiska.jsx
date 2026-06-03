import { useEffect, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm } from '../../lib/format'

// Wiersz tabeli stanowisk z edycją inline. Lokalny stan seedowany z propsów
// (klucz=id => świeży stan po przeładowaniu listy).
function StanowiskoRow({ s, onChanged }) {
  const { toast, confirm } = useToast()
  const [nazwa, setNazwa] = useState(s.nazwa)
  const [weekend, setWeekend] = useState(s.tylko_weekend)
  const [busy, setBusy] = useState(false)

  const zapisz = async () => {
    setBusy(true)
    try {
      await api(`/stanowiska/${s.id}`, 'PUT', { nazwa: nazwa.trim(), tylko_weekend: weekend })
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
    <tr className="transition hover:bg-white/[0.02]">
      <td className="px-4 py-3 font-mono text-xs text-muted">#{s.id}</td>
      <td className="px-4 py-3">
        <input value={nazwa} onChange={(e) => setNazwa(e.target.value)} className="field max-w-[240px] py-2" />
      </td>
      <td className="px-4 py-3 text-center">
        <input type="checkbox" checked={weekend} onChange={(e) => setWeekend(e.target.checked)} className="h-4 w-4 accent-mint" />
      </td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={zapisz} disabled={busy}>
            <Icon name="check" className="h-4 w-4" /> Zapisz
          </Button>
          <Button size="sm" variant="danger" onClick={usun} aria-label="Usuń stanowisko">
            <Icon name="trash" className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

export default function Stanowiska() {
  const { stanowiska, reloadDicts } = useData()
  const { toast } = useToast()
  const [nowa, setNowa] = useState('')
  const [nowaWeekend, setNowaWeekend] = useState(false)
  const [pkStan, setPkStan] = useState('')
  const [pkNazwa, setPkNazwa] = useState('')
  const [pkOd, setPkOd] = useState('')

  useEffect(() => {
    reloadDicts()
  }, [reloadDicts])

  const dodajStanowisko = async () => {
    if (!nowa.trim()) return
    try {
      await api('/stanowiska', 'POST', { nazwa: nowa.trim(), tylko_weekend: nowaWeekend })
      setNowa('')
      setNowaWeekend(false)
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
      {/* Nowe stanowisko */}
      <Card className="p-8">
        <h3 className="mb-5 font-display text-lg font-bold text-ink">Nowe stanowisko (kategoria główna)</h3>
        <div className="flex flex-wrap items-center gap-4">
          <input
            value={nowa}
            onChange={(e) => setNowa(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && dodajStanowisko()}
            placeholder="Np. Sala, Bar…"
            className="field w-64"
          />
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm font-medium text-ink">
            <input type="checkbox" checked={nowaWeekend} onChange={(e) => setNowaWeekend(e.target.checked)} className="h-4 w-4 accent-mint" />
            Tylko weekend
          </label>
          <Button onClick={dodajStanowisko}>
            <Icon name="plus" className="h-4 w-4" /> Dodaj stanowisko
          </Button>
        </div>
      </Card>

      {/* Lista stanowisk */}
      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-4 font-semibold">ID</th>
              <th className="px-4 py-4 font-semibold">Nazwa</th>
              <th className="px-4 py-4 text-center font-semibold">Tylko weekend</th>
              <th className="px-4 py-4 text-right font-semibold">Akcje</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {stanowiska.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-muted">Brak stanowisk. Dodaj pierwsze powyżej.</td>
              </tr>
            ) : (
              stanowiska.map((s) => <StanowiskoRow key={s.id} s={s} onChanged={reloadDicts} />)
            )}
          </tbody>
        </table>
      </Card>

      {/* Szablony rewirów / zmian */}
      <Card className="p-8">
        <SectionHeader title="Szablony rewirów / zmian" subtitle="Przypisz gotowe rewiry i godziny wejścia do istniejących stanowisk." />
        <div className="mb-8 flex flex-wrap items-end gap-4 rounded-2xl border border-line bg-surface-2/60 p-5">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Stanowisko</span>
            <select value={pkStan} onChange={(e) => setPkStan(e.target.value)} className="field min-w-[180px]">
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
          <Button variant="accent" onClick={dodajSzablon}>
            <Icon name="plus" className="h-4 w-4" /> Dodaj szablon
          </Button>
        </div>

        {zSzablonami.length === 0 ? (
          <p className="text-sm text-muted">Brak zdefiniowanych szablonów rewirów.</p>
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
