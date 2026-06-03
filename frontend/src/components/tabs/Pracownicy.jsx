import { useEffect, useState } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

// Rozwijana lista kwalifikacji (checkboxy stanowisk).
function KwalifikacjeDropdown({ stanowiska, selected, onToggle }) {
  return (
    <details className="group rounded-xl border border-line bg-surface-2">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-medium text-ink outline-none [&::-webkit-details-marker]:hidden">
        Wybierz kwalifikacje ({selected.length})
        <Icon name="chevronDown" className="h-4 w-4 text-muted transition group-open:rotate-180" />
      </summary>
      <div className="grid max-h-44 grid-cols-2 gap-1 overflow-y-auto border-t border-line p-3 lg:grid-cols-3">
        {stanowiska.map((s) => (
          <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded-lg p-1.5 text-xs hover:bg-white/[0.05]">
            <input type="checkbox" checked={selected.includes(s.id)} onChange={() => onToggle(s.id)} className="h-3.5 w-3.5 accent-mint" />
            <span className="truncate">{s.nazwa}</span>
          </label>
        ))}
      </div>
    </details>
  )
}

function PracownikRow({ p, stanowiska, onChanged }) {
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
    <tr className="align-top transition hover:bg-white/[0.02]">
      <td className="px-4 py-4">
        <div className="flex flex-col gap-1">
          <input value={imie} onChange={(e) => setImie(e.target.value)} className="w-full border-b border-transparent bg-transparent text-base font-bold text-ink outline-none focus:border-mint/60" />
          <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} className="w-full border-b border-transparent bg-transparent text-xs font-medium text-muted outline-none focus:border-mint/60" />
        </div>
      </td>
      <td className="px-4 py-4 text-center">
        <input type="checkbox" checked={aktywny} onChange={(e) => setAktywny(e.target.checked)} className="h-5 w-5 accent-success" aria-label="Aktywny" />
      </td>
      <td className="px-4 py-4">
        <KwalifikacjeDropdown stanowiska={stanowiska} selected={kwal} onToggle={toggle} />
      </td>
      <td className="px-4 py-4">
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={zapisz} disabled={busy}>
            <Icon name="check" className="h-4 w-4" /> Zapisz
          </Button>
          <Button size="sm" variant="danger" onClick={usun} aria-label="Usuń pracownika">
            <Icon name="trash" className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
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
      {/* Dodaj pracownika */}
      <Card className="border-dashed p-6">
        <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-bold text-ink">
          <Icon name="plus" className="h-5 w-5 text-mint" /> Dodaj pracownika
        </h3>
        <div className="flex flex-col items-start gap-4 md:flex-row md:items-center">
          <input value={imie} onChange={(e) => setImie(e.target.value)} placeholder="Imię" className="field md:w-48" />
          <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} placeholder="Nazwisko" className="field md:w-48" />
          <div className="w-full flex-1">
            <KwalifikacjeDropdown stanowiska={stanowiska} selected={kwal} onToggle={toggle} />
          </div>
          <Button onClick={utworz} className="w-full whitespace-nowrap md:w-auto">
            Utwórz konto
          </Button>
        </div>
      </Card>

      {/* Lista pracowników */}
      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-4 font-semibold">Imię i nazwisko</th>
              <th className="w-24 px-4 py-4 text-center font-semibold">Aktywny</th>
              <th className="px-4 py-4 font-semibold">Kwalifikacje</th>
              <th className="w-48 px-4 py-4 text-right font-semibold">Akcje</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {pracownicy.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-muted">Brak pracowników. Dodaj pierwszego powyżej.</td>
              </tr>
            ) : (
              pracownicy.map((p) => <PracownikRow key={p.id} p={p} stanowiska={stanowiska} onChanged={reloadDicts} />)
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
