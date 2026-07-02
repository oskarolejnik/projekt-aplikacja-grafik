import { useEffect, useState, useCallback } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { tloKoloru } from '../../lib/format'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

// Paleta tła pracownika (ręcznie, bez algorytmów) — przyjazne dla ciemnego motywu.
const PALETA = ['#f472b6', '#fb923c', '#fbbf24', '#34d399', '#60a5fa', '#a78bfa', '#f87171', '#22d3ee']

function KolorPicker({ value, onChange }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => onChange(null)}
        title="brak koloru"
        className={`grid h-7 w-7 place-items-center rounded-full border-2 text-muted transition ${!value ? 'border-ink' : 'border-line'}`}
      >
        <Icon name="close" className="h-3 w-3" />
      </button>
      {PALETA.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          title={c}
          className={`h-7 w-7 rounded-full border-2 transition ${value === c ? 'scale-110 border-ink' : 'border-line'}`}
          style={{ background: c + '66' }}
        />
      ))}
    </div>
  )
}

// Wybór działu: obsługa (stanowiska + stawki per stanowisko) lub kuchnia (bez stanowisk, jedna stawka).
function DzialPicker({ value, onChange }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="field-label">Dział (osobny grafik)</span>
      <div className="grid grid-cols-3 gap-2">
        {[
          ['obsluga', 'Obsługa'],
          ['kuchnia', 'Kuchnia'],
          ['techniczny', 'Techniczny'],
        ].map(([v, label]) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
              value === v ? 'border-mint bg-mint/15 text-mint' : 'border-line bg-surface-2 text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </label>
  )
}

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

// Stawki godzinowe (zł/h) dla zaznaczonych kwalifikacji. Ta sama kwalifikacja może mieć różną stawkę u różnych osób.
function StawkiEdytor({ stanowiska, kwal, stawki, setStawka }) {
  if (kwal.length === 0) return null
  const nazwa = (id) => stanowiska.find((s) => s.id === id)?.nazwa || `#${id}`
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface-2 p-3">
      <span className="field-label">Stawki godzinowe</span>
      {kwal.map((id) => (
        <div key={id} className="flex items-center justify-between gap-3 text-sm">
          <span className="min-w-0 truncate text-ink">{nazwa(id)}</span>
          <div className="flex shrink-0 items-center gap-1.5">
            <input
              type="number"
              min="0"
              step="0.50"
              inputMode="decimal"
              value={stawki[id] ?? ''}
              onChange={(e) => setStawka(id, e.target.value)}
              placeholder="0"
              className="field w-24 px-2 py-1.5 text-right"
            />
            <span className="text-xs text-muted">zł/h</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// Pojedyncza stawka godzinowa (kuchnia/techniczny — bez stanowisk; różne osoby, różne stawki).
function StawkaJedna({ label, value, onChange }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface-2 p-3">
      <span className="field-label">{label}</span>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          min="0"
          step="0.50"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="0"
          className="field w-28 px-2 py-1.5 text-right"
        />
        <span className="text-xs text-muted">zł/h</span>
      </div>
    </div>
  )
}

// Zbiera stawki tylko dla zaznaczonych kwalifikacji -> format API: [{stanowisko_id, stawka}].
const zbierzStawki = (kwal, stawki) =>
  kwal.map((id) => ({ stanowisko_id: id, stawka: parseFloat(stawki[id]) || 0 }))

function PracownikRow({ p, i, stanowiska, dzialIds, onChanged, onMove, first, last }) {
  const { toast, confirm } = useToast()
  const [imie, setImie] = useState(p.imie)
  const [nazwisko, setNazwisko] = useState(p.nazwisko)
  const [aktywny, setAktywny] = useState(p.aktywny)
  const [kolor, setKolor] = useState(p.kolor || null)
  const [dzial, setDzial] = useState(p.dzial || 'obsluga')
  const [kwal, setKwal] = useState((p.kwalifikacje || []).map((k) => k.id))
  const [stawki, setStawki] = useState(() =>
    Object.fromEntries((p.stawki || []).map((s) => [s.stanowisko_id, String(s.stawka)])),
  )
  const [stawkaJedna, setStawkaJedna] = useState('')
  const [busy, setBusy] = useState(false)

  const jednaStawka = dzial === 'kuchnia' || dzial === 'techniczny'  // główna stawka bez stanowisk
  const stanId = dzialIds[dzial]  // id ukrytego stanowiska (Kuchnia / Techniczny)
  const ukryte = [dzialIds.kuchnia, dzialIds.techniczny].filter(Boolean)
  const stanowiskaObslugi = stanowiska.filter((s) => !ukryte.includes(s.id))   // kwalifikacje obsługi
  const stanowiskaDodatkowe = stanowiska.filter((s) => s.id !== stanId)        // dodatkowe stawki (też drugi ukryty)

  // Główna stawka (z ukrytego stanowiska działu) + dodatkowe (inne stanowiska) z zapisanych stawek.
  useEffect(() => {
    if (!stanId) return
    const prim = (p.stawki || []).find((x) => x.stanowisko_id === stanId)
    setStawkaJedna(prim ? String(prim.stawka) : '')
    if (jednaStawka) {
      setKwal((p.stawki || []).map((x) => x.stanowisko_id).filter((id) => id !== stanId))
    }
  }, [stanId, jednaStawka, p.stawki])

  const toggle = (id) => setKwal((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  const setStawka = (id, val) => setStawki((cur) => ({ ...cur, [id]: val }))

  const zapisz = async () => {
    setBusy(true)
    try {
      await api(`/pracownicy/${p.id}`, 'PUT', {
        imie: imie.trim(),
        nazwisko: nazwisko.trim(),
        aktywny,
        kolor,
        dzial,
        kwalifikacje_ids: jednaStawka ? [] : kwal,
        stawki: jednaStawka
          ? [
              ...(stanId && parseFloat(stawkaJedna) > 0 ? [{ stanowisko_id: stanId, stawka: parseFloat(stawkaJedna) }] : []),
              ...zbierzStawki(kwal, stawki),  // dodatkowe stawki (inne stanowiska)
            ]
          : zbierzStawki(kwal, stawki),
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
    if (!(await confirm(`Usunąć pracownika „${p.imie} ${p.nazwisko}”?`))) return
    try {
      await api(`/pracownicy/${p.id}`, 'DELETE')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div
      className="animate-fade-up overflow-hidden rounded-2xl border border-line bg-white/[0.02] p-4"
      style={{ animationDelay: `${Math.min(i, 8) * 45}ms`, borderLeft: kolor ? `4px solid ${kolor}` : undefined }}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          {/* Strzałki kolejności */}
          <div className="flex shrink-0 flex-col gap-1">
            <button onClick={() => onMove(p.id, -1)} disabled={first} className="rounded-md border border-line p-1 text-muted transition hover:text-ink disabled:opacity-30" aria-label="W górę">
              <Icon name="chevronDown" className="h-3.5 w-3.5 rotate-180" />
            </button>
            <button onClick={() => onMove(p.id, 1)} disabled={last} className="rounded-md border border-line p-1 text-muted transition hover:text-ink disabled:opacity-30" aria-label="W dół">
              <Icon name="chevronDown" className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex flex-1 flex-col gap-1 rounded-lg px-2 py-1" style={{ background: tloKoloru(kolor) }}>
            <input value={imie} onChange={(e) => setImie(e.target.value)} placeholder="Imię" className="w-full border-b border-transparent bg-transparent text-base font-bold text-ink outline-none focus:border-mint/60" />
            <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} placeholder="Nazwisko" className="w-full border-b border-transparent bg-transparent text-xs font-medium text-muted outline-none focus:border-mint/60" />
          </div>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2 text-xs font-medium text-ink">
            <input type="checkbox" checked={aktywny} onChange={(e) => setAktywny(e.target.checked)} className="h-4 w-4 accent-success" />
            Aktywny
          </label>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="field-label">Kolor tła (ręcznie)</span>
          <KolorPicker value={kolor} onChange={setKolor} />
        </label>

        <DzialPicker value={dzial} onChange={setDzial} />

        {jednaStawka ? (
          <>
            <StawkaJedna label={dzial === 'kuchnia' ? 'Stawka (kuchnia)' : 'Stawka (techniczny)'} value={stawkaJedna} onChange={setStawkaJedna} />
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Dodatkowe stawki (gdy pracuje na innym stanowisku)</span>
              <KwalifikacjeDropdown stanowiska={stanowiskaDodatkowe} selected={kwal} onToggle={toggle} />
            </label>
            <StawkiEdytor stanowiska={stanowiskaDodatkowe} kwal={kwal} stawki={stawki} setStawka={setStawka} />
          </>
        ) : (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Kwalifikacje</span>
              <KwalifikacjeDropdown stanowiska={stanowiskaObslugi} selected={kwal} onToggle={toggle} />
            </label>
            <StawkiEdytor stanowiska={stanowiskaObslugi} kwal={kwal} stawki={stawki} setStawka={setStawka} />
          </>
        )}

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
  const [kolor, setKolor] = useState(null)
  const [dzial, setDzial] = useState('obsluga')
  const [kwal, setKwal] = useState([])
  const [stawki, setStawki] = useState({})
  const [stawkaJedna, setStawkaJedna] = useState('')
  const [dzialIds, setDzialIds] = useState({})  // { kuchnia, techniczny } — ukryte stanowiska

  useEffect(() => {
    reloadDicts()
    // Id ukrytych stanowisk (tworzone leniwie) — do stawki kuchni/technicznej.
    Promise.all([
      api('/grafik/kuchnia-stanowisko').catch(() => null),
      api('/grafik/techniczny-stanowisko').catch(() => null),
    ]).then(([k, t]) => setDzialIds({ kuchnia: k?.id, techniczny: t?.id }))
  }, [reloadDicts])

  const jednaStawka = dzial === 'kuchnia' || dzial === 'techniczny'
  const stanId = dzialIds[dzial]
  // W kwalifikacjach obsługi nie pokazujemy ukrytych stanowisk (Kuchnia / Techniczny).
  const stanowiskaObslugi = stanowiska.filter((s) => ![dzialIds.kuchnia, dzialIds.techniczny].includes(s.id))
  const stanowiskaDodatkowe = stanowiska.filter((s) => s.id !== stanId)  // dodatkowe stawki (też drugi ukryty)

  const toggle = (id) => setKwal((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  const setStawka = (id, val) => setStawki((cur) => ({ ...cur, [id]: val }))

  // Zmiana kolejności: zamień sąsiadów i zapisz całą listę id.
  const przesun = useCallback(
    async (pid, kierunek) => {
      const lista = [...pracownicy]
      const i = lista.findIndex((p) => p.id === pid)
      const j = i + kierunek
      if (i < 0 || j < 0 || j >= lista.length) return
      ;[lista[i], lista[j]] = [lista[j], lista[i]]
      try {
        await api('/pracownicy/kolejnosc', 'PUT', { ids: lista.map((p) => p.id) })
        reloadDicts()
      } catch (e) {
        toast(e.message, 'error')
      }
    },
    [pracownicy, reloadDicts, toast],
  )

  const utworz = async () => {
    if (!imie.trim() || !nazwisko.trim()) {
      toast('Podaj imię i nazwisko.', 'error')
      return
    }
    try {
      await api('/pracownicy', 'POST', {
        imie: imie.trim(),
        nazwisko: nazwisko.trim(),
        aktywny: true,
        kolor,
        dzial,
        kwalifikacje_ids: jednaStawka ? [] : kwal,
        stawki: jednaStawka
          ? [
              ...(stanId && parseFloat(stawkaJedna) > 0 ? [{ stanowisko_id: stanId, stawka: parseFloat(stawkaJedna) }] : []),
              ...zbierzStawki(kwal, stawki),
            ]
          : zbierzStawki(kwal, stawki),
      })
      setImie('')
      setNazwisko('')
      setKolor(null)
      setDzial('obsluga')
      setKwal([])
      setStawki({})
      setStawkaJedna('')
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
          <KolorPicker value={kolor} onChange={setKolor} />
          <DzialPicker value={dzial} onChange={setDzial} />
          {jednaStawka ? (
            <>
              <StawkaJedna label={dzial === 'kuchnia' ? 'Stawka (kuchnia)' : 'Stawka (techniczny)'} value={stawkaJedna} onChange={setStawkaJedna} />
              <span className="field-label -mb-2">Dodatkowe stawki (inne stanowiska)</span>
              <KwalifikacjeDropdown stanowiska={stanowiskaDodatkowe} selected={kwal} onToggle={toggle} />
              <StawkiEdytor stanowiska={stanowiskaDodatkowe} kwal={kwal} stawki={stawki} setStawka={setStawka} />
            </>
          ) : (
            <>
              <KwalifikacjeDropdown stanowiska={stanowiskaObslugi} selected={kwal} onToggle={toggle} />
              <StawkiEdytor stanowiska={stanowiskaObslugi} kwal={kwal} stawki={stawki} setStawka={setStawka} />
            </>
          )}
          <Button onClick={utworz} className="w-full">
            <Icon name="plus" className="h-4 w-4" /> Utwórz pracownika
          </Button>
        </div>
      </Card>

      {/* Lista pracowników — karty. Kolejność strzałkami ↑/↓, kolor tła za imieniem. */}
      <div className="space-y-3">
        {pracownicy.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted">Brak pracowników. Dodaj pierwszego powyżej.</Card>
        ) : (
          pracownicy.map((p, i) => (
            <PracownikRow
              key={p.id}
              p={p}
              i={i}
              stanowiska={stanowiska}
              dzialIds={dzialIds}
              onChanged={reloadDicts}
              onMove={przesun}
              first={i === 0}
              last={i === pracownicy.length - 1}
            />
          ))
        )}
      </div>
    </div>
  )
}
