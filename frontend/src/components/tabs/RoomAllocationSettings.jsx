import { useEffect, useMemo, useState } from 'react'
import { Button } from '../ui/Button'

const roomDraft = (room = {}) => ({
  nazwa: String(room.nazwa || ''),
  aktywna: room.aktywna !== false,
  kolejnosc: Math.max(0, Math.round(Number(room.kolejnosc) || 0)),
  strategia_zapelniania: room.strategia_zapelniania === 'wypelniaj_kolejno'
    ? 'wypelniaj_kolejno'
    : 'preferuj',
  priorytet: Math.max(0, Math.round(Number(room.priorytet) || 0)),
})

export default function RoomAllocationSettings({
  room,
  disabled = false,
  saving = false,
  feedback = null,
  onSave,
  onDirtyChange,
}) {
  // Odświeżenie listy sal zwraca nowe obiekty także wtedy, gdy wartości się nie
  // zmieniły. Zależności skalarne chronią lokalny szkic przed cichym resetem.
  const initial = useMemo(() => roomDraft(room), [
    room?.id,
    room?.nazwa,
    room?.aktywna,
    room?.kolejnosc,
    room?.strategia_zapelniania,
    room?.priorytet,
  ])
  const [draft, setDraft] = useState(initial)

  useEffect(() => setDraft(initial), [initial])

  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)

  useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
  }, [dirty, onDirtyChange])

  const update = (patch) => setDraft((current) => ({ ...current, ...patch }))

  const submit = (event) => {
    event.preventDefault()
    if (!dirty || disabled || saving || !draft.nazwa.trim()) return
    onSave?.({
      ...draft,
      nazwa: draft.nazwa.trim(),
    })
  }

  return (
    <form onSubmit={submit} className="mt-5 border-y border-line py-5" aria-labelledby="room-allocation-settings-heading">
      <div className="max-w-3xl">
        <h4 id="room-allocation-settings-heading" className="text-base font-semibold text-ink">
          Ustawienia obsadzania sali
        </h4>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          Określ, kiedy automat ma wybierać tę salę. Ręczny przydział obsługi pozostaje zawsze możliwy.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Nazwa sali
            <input
              value={draft.nazwa}
              onChange={(event) => update({ nazwa: event.target.value })}
              maxLength={32}
              required
              disabled={disabled || saving}
              className="field mt-1.5 min-h-11 normal-case tracking-normal"
            />
          </label>

          <label className="field-label">
            Kolejność obsadzania
            <input
              type="number"
              min="1"
              value={draft.priorytet + 1}
              onChange={(event) => update({
                priorytet: Math.max(0, Math.round(Number(event.target.value) || 1) - 1),
              })}
              disabled={disabled || saving}
              className="field mt-1.5 min-h-11 normal-case tracking-normal"
            />
            <span className="mt-1.5 block text-xs font-normal normal-case leading-relaxed tracking-normal text-muted">
              1 oznacza salę wybieraną najwcześniej.
            </span>
          </label>

          <label className="field-label sm:col-span-2">
            Sposób zapełniania
            <select
              value={draft.strategia_zapelniania}
              onChange={(event) => update({ strategia_zapelniania: event.target.value })}
              disabled={disabled || saving}
              className="field mt-1.5 min-h-11 normal-case tracking-normal"
            >
              <option value="preferuj">Preferuj, ale pozwól wybrać lepiej dopasowany stół</option>
              <option value="wypelniaj_kolejno">Wypełniaj tę salę przed kolejnymi</option>
            </select>
            <span className="mt-1.5 block text-xs font-normal normal-case leading-relaxed tracking-normal text-muted">
              {draft.strategia_zapelniania === 'wypelniaj_kolejno'
                ? 'Dopóki ta sala ma bezpieczny wolny zestaw, automat nie przejdzie do dalszej sali.'
                : 'Lepsze dopasowanie liczby miejsc może wygrać z kolejnością sal.'}
            </span>
          </label>

          <label className="flex min-h-11 items-start gap-3 rounded-xl border border-line bg-white/[0.025] px-3 py-3 text-sm text-ink sm:col-span-2">
            <input
              type="checkbox"
              checked={draft.aktywna}
              onChange={(event) => update({ aktywna: event.target.checked })}
              disabled={disabled || saving}
              className="mt-0.5 h-5 w-5 shrink-0 accent-mint"
            />
            <span>
              <span className="block font-semibold">Przyjmuj nowe rezerwacje w tej sali</span>
              <span className="mt-1 block text-xs leading-relaxed text-muted">
                Wyłączenie nie usuwa planu ani już przypisanych rezerwacji.
              </span>
            </span>
          </label>
        </div>

        {feedback ? (
          <p
            className={`mt-4 text-sm ${feedback.type === 'error' ? 'text-danger' : 'text-success'}`}
            role={feedback.type === 'error' ? 'alert' : 'status'}
          >
            {feedback.message}
          </p>
        ) : null}

        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDraft(initial)}
            disabled={disabled || saving || !dirty}
          >
            Przywróć
          </Button>
          <Button
            type="submit"
            variant="subtle"
            size="sm"
            loading={saving}
            loadingLabel="Zapisuję…"
            disabled={disabled || saving || !dirty || !draft.nazwa.trim()}
          >
            Zapisz ustawienia
          </Button>
        </div>
      </div>
    </form>
  )
}
