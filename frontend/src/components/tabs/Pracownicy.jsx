import { useEffect, useState } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

// Rozwijana lista kwalifikacji (checkboxy stanowisk). Pełna szerokość = czytelne nazwy.
function KwalifikacjeDropdown({ stanowiska, selected, onToggle }) {
  return (
    <details className="group rounded-xl border border-line bg-surface-2">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-sm font-medium text-ink outline-none [&::-webkit-details-marker]:hidden">
        <span>Wybierz kwalifikacje ({selected.length})</span>
        <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" />
      </summary>
      <div className="grid max-h-52 grid-cols-1 gap-1 overflow-y-auto border-t border-line p-3 sm:grid-cols-2 lg:grid-cols-3">
        {stanowiska.length === 0 ? (
          <span className="p-1.5 text-xs text-muted">Brak stanowisk — dodaj je w zakładce „Stanowiska".</span>
        ) : (
          stanowiska.map((s) => (
            <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded-lg p-2 text-sm hover:bg-white/[0.05]">
              <input type="checkbox" checked={selected.includes(s.id)} onChange={() => onToggle(s.id)} className="h-4 w-4 shrink-0 accent-mint" />
              <span className="truncate">{s.nazwa}</span>
            </label>
          ))
        )}
      </div>
    </details>
  )
}

function PracownikRow({ p, i, stanowiska, onChanged }) {
  const { toast, confirm } = useToast()
  const [imie, setImie] = useState(p.imie)
  const [nazwisko, setNazwisko] = useState(p.nazwisko)
  const [aktywny, setAktywny] = useState(p.aktywny)
  const [kwal, setKwal] = useState((p.kwalifikacje || []).map((k) => k.id))
  const [busy, setBusy] = useState(false)

  const toggle = (id) => setKwal((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  const zapisz = async () => {
    setBusy(true)
    try {
      await api(`/pracownicy/${p.id}`, 'PUT', { imie: imie.trim(), nazwisko: nazwisko.trim(), aktywny, kwalifikacje_ids: kwal })
      toast('Zapisano zmiany.', 'success')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }
  const usun = async () => {
    if (!(await confirm(`Usunąć pracownika „${p.imie} ${p.nazwisko}”?`))) return
    try {
      await api(`/pracownicy/${p.id}`, 'DELETE')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div className="animate-fade-up rounded-2xl border border-line bg-white/[0.02] p-4" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-1 flex-col gap-1">
            <input value={imie} onChange={(e) => setImie(e.target.value)} placeholder="Imię" className="w-full border-b border-transparent bg-transparent text-base font-bold text-ink outline-none focus:border-mint/60" />
            <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} placeholder="Nazwisko" className="w-full border-b border-transparent bg-transparent text-xs font-medium text-muted outline-none focus:border-mint/60" />
          </div>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink">
            <input type="checkbox" checked={aktywny} onChange={(e) => setAktywny(e.target.checked)} className="h-4 w-4 accent-success" />
            Aktywny
          </label>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="field-label">Kwalifikacje</span>
          <KwalifikacjeDropdown stanowiska={stanowiska} selected={kwal} onToggle={toggle} />
        </label>

        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={zapisz} disabled={busy}>
            <Icon name="check" className="h-4 w-4" /> Zapisz
          </Button>
          <Button size="sm" variant="danger" onClick={usun} aria-label="Usuń pracownika">
            <Icon name="trash" className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function Pracownicy() {
  const { stanowiska, pracownicy, reloadDicts } = useData()
  const { toast } = useToast()
  const [imie, setImie] = useState('')
  const [nazwisko, setNazwisko] = useState('')
  const [kwal, setKwal] = useState([])

  useEffect(() => {
    reloadDicts()
  }, [reloadDicts])

  const toggle = (id) => setKwal((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  const utworz = async () => {
    if (!imie.trim() || !nazwisko.trim()) {
      toast('Podaj imię i nazwisko.', 'error')
      return
    }
    try {
      await api('/pracownicy', 'POST', { imie: imie.trim(), nazwisko: nazwisko.trim(), aktywny: true, kwalifikacje_ids: kwal })
      setImie('')
      setNazwisko('')
      setKwal([])
      reloadDicts()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div className="space-y-8">
      {/* Dodaj pracownika — wyśrodkowana kolumna */}
      <Card className="border-dashed p-6 sm:p-8">
        <h3 className="mb-5 flex items-center justify-center gap-2 font-display text-lg font-bold text-ink">
          <Icon name="plus" className="h-5 w-5 text-mint" /> Dodaj pracownika
        </h3>
        <div className="mx-auto flex max-w-md flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <input value={imie} onChange={(e) => setImie(e.target.value)} placeholder="Imię" className="field" />
            <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} placeholder="Nazwisko" className="field" />
          </div>
          <KwalifikacjeDropdown stanowiska={stanowiska} selected={kwal} onToggle={toggle} />
          <Button onClick={utworz} className="w-full">
            <Icon name="plus" className="h-4 w-4" /> Utwórz pracownika
          </Button>
        </div>
      </Card>

      {/* Lista pracowników — karty (czytelne na mobile, kwalifikacje pełnej szerokości) */}
      <div className="space-y-3">
        {pracownicy.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted">Brak pracowników. Dodaj pierwszego powyżej.</Card>
        ) : (
          pracownicy.map((p, i) => <PracownikRow key={p.id} p={p} i={i} stanowiska={stanowiska} onChanged={reloadDicts} />)
        )}
      </div>
    </div>
  )
}
