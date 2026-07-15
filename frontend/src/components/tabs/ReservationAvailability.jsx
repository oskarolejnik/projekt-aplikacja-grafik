import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { localDateIso } from '../../lib/reservationRoute'
import { registerReservationLeaveGuard } from '../../lib/reservationLeaveGuard'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { Icon } from '../../lib/icons'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import ReservationAllocationSummary from './ReservationAllocationSummary'

const DAYS = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
const DAY_SHORT = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd']

const toTime = (value, fallback = '') => String(value || fallback).slice(0, 5)
const toNumber = (value, fallback = 0) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}
const optionalNumber = (value) => value === '' || value == null ? null : Math.max(0, Math.round(toNumber(value)))
const optionalPositiveNumber = (value) => value === '' || value == null ? null : Math.max(1, Math.round(toNumber(value, 1)))

const policyFrom = (value = {}) => ({
  okno_wyprzedzenia_dni: Math.max(0, Math.round(toNumber(value.okno_wyprzedzenia_dni ?? value.rez_okno_wyprzedzenia_dni, 90))),
  cutoff_min: Math.max(0, Math.round(toNumber(value.cutoff_min ?? value.rez_cutoff_min, 60))),
  bufor_min: Math.max(0, Math.round(toNumber(value.bufor_min ?? value.rez_bufor_min, 0))),
  min_grupa_online: Math.max(1, Math.round(toNumber(value.min_grupa_online ?? value.rez_min_grupa_online, 1))),
  max_grupa_online: Math.max(0, Math.round(toNumber(value.max_grupa_online ?? value.rez_max_grupa_online, 20))),
})

const policyPayload = (value) => ({
  okno_wyprzedzenia_dni: Math.max(0, Math.round(toNumber(value.okno_wyprzedzenia_dni))),
  cutoff_min: Math.max(0, Math.round(toNumber(value.cutoff_min))),
  bufor_min: Math.max(0, Math.round(toNumber(value.bufor_min))),
  min_grupa_online: Math.max(1, Math.round(toNumber(value.min_grupa_online, 1))),
  max_grupa_online: Math.max(0, Math.round(toNumber(value.max_grupa_online))),
})

const emptyService = () => ({
  nazwa: 'Kolacja',
  days: [4, 5],
  godz_od: '17:00',
  godz_do: '23:00',
  ostatni_zasiadek: '21:30',
  krok_slotu_min: 15,
  domyslny_turn_time_min: 120,
  turn_2: 90,
  turn_4: 120,
  turn_large: 150,
  pacing_okno_min: 30,
  pacing_max_rez: '',
  pacing_max_osob: '',
  max_jednoczesnych_rez: '',
  max_jednoczesnych_osob: '',
  duza_grupa_od: '',
  duza_grupa_tryb: 'do_zatwierdzenia',
  aktywny: true,
})

const serviceFrom = (row = {}) => {
  const thresholds = [...(row.turn_time_progi || [])].sort((a, b) => Number(a.do_osob) - Number(b.do_osob))
  const duration = row.domyslny_turn_time_min ?? row.dlugosc_slotu_min ?? 120
  const durationFor = (people, fallback) => thresholds.find((item) => Number(item.do_osob) >= people)?.min ?? fallback
  return {
    nazwa: row.nazwa || 'Serwis',
    days: [Math.max(0, Math.min(6, Number(row.dzien_tygodnia) || 0))],
    godz_od: toTime(row.godz_od, '12:00'),
    godz_do: toTime(row.godz_do, '22:00'),
    ostatni_zasiadek: toTime(row.ostatni_zasiadek, ''),
    krok_slotu_min: Math.max(5, toNumber(row.krok_slotu_min ?? row.dlugosc_slotu_min, 15)),
    domyslny_turn_time_min: Math.max(15, toNumber(duration, 120)),
    turn_2: durationFor(2, duration),
    turn_4: durationFor(4, duration),
    turn_large: thresholds.at(-1)?.min ?? duration,
    pacing_okno_min: Math.max(5, toNumber(row.pacing_okno_min ?? row.krok_slotu_min, 30)),
    pacing_max_rez: row.pacing_max_rez ?? '',
    pacing_max_osob: row.pacing_max_osob ?? '',
    max_jednoczesnych_rez: row.max_jednoczesnych_rez ?? '',
    max_jednoczesnych_osob: row.max_jednoczesnych_osob ?? '',
    duza_grupa_od: row.duza_grupa_od ?? '',
    duza_grupa_tryb: row.duza_grupa_tryb || 'do_zatwierdzenia',
    aktywny: row.aktywny !== false,
  }
}

const servicePayload = (draft, day) => {
  const largePartyFrom = optionalPositiveNumber(draft.duza_grupa_od)
  return {
    dzien_tygodnia: Number(day),
    nazwa: draft.nazwa.trim() || null,
    godz_od: draft.godz_od,
    godz_do: draft.godz_do,
    ostatni_zasiadek: draft.ostatni_zasiadek || null,
    krok_slotu_min: Math.max(5, Math.round(toNumber(draft.krok_slotu_min, 15))),
    domyslny_turn_time_min: Math.max(15, Math.round(toNumber(draft.domyslny_turn_time_min, 120))),
    turn_time_progi: [
      { do_osob: 2, min: Math.max(15, Math.round(toNumber(draft.turn_2, 90))) },
      { do_osob: 4, min: Math.max(15, Math.round(toNumber(draft.turn_4, 120))) },
      { do_osob: 999, min: Math.max(15, Math.round(toNumber(draft.turn_large, 150))) },
    ],
    pacing_okno_min: Math.max(5, Math.round(toNumber(draft.pacing_okno_min, 30))),
    pacing_max_rez: optionalNumber(draft.pacing_max_rez),
    pacing_max_osob: optionalNumber(draft.pacing_max_osob),
    max_jednoczesnych_rez: optionalNumber(draft.max_jednoczesnych_rez),
    max_jednoczesnych_osob: optionalNumber(draft.max_jednoczesnych_osob),
    duza_grupa_od: largePartyFrom,
    duza_grupa_tryb: largePartyFrom == null ? null : draft.duza_grupa_tryb,
    aktywny: draft.aktywny !== false,
  }
}

const emptyOverride = () => ({
  serwis_id: '',
  sala_id: '',
  kanal: 'oba',
  pacing_okno_min: '',
  pacing_max_rez: '',
  pacing_max_osob: '',
  max_jednoczesnych_rez: '',
  max_jednoczesnych_osob: '',
  bufor_min: '',
  okno_wyprzedzenia_dni: '',
  cutoff_min: '',
  min_grupa: '',
  max_grupa: '',
  duza_grupa_od: '',
  duza_grupa_tryb: 'do_zatwierdzenia',
})

const overrideFrom = (row = {}) => ({
  serwis_id: row.serwis_id ?? '',
  sala_id: row.sala_id ?? '',
  kanal: row.kanal || 'oba',
  pacing_okno_min: row.pacing_okno_min ?? '',
  pacing_max_rez: row.pacing_max_rez ?? '',
  pacing_max_osob: row.pacing_max_osob ?? '',
  max_jednoczesnych_rez: row.max_jednoczesnych_rez ?? '',
  max_jednoczesnych_osob: row.max_jednoczesnych_osob ?? '',
  bufor_min: row.bufor_min ?? '',
  okno_wyprzedzenia_dni: row.okno_wyprzedzenia_dni ?? '',
  cutoff_min: row.cutoff_min ?? '',
  min_grupa: row.min_grupa ?? '',
  max_grupa: row.max_grupa ?? '',
  duza_grupa_od: row.duza_grupa_od ?? '',
  duza_grupa_tryb: row.duza_grupa_tryb || 'do_zatwierdzenia',
})

const overridePayload = (draft) => {
  const largePartyFrom = optionalPositiveNumber(draft.duza_grupa_od)
  return {
    serwis_id: draft.serwis_id === '' ? null : Number(draft.serwis_id),
    sala_id: draft.sala_id === '' ? null : Number(draft.sala_id),
    kanal: draft.kanal,
    pacing_okno_min: optionalNumber(draft.pacing_okno_min),
    pacing_max_rez: optionalNumber(draft.pacing_max_rez),
    pacing_max_osob: optionalNumber(draft.pacing_max_osob),
    max_jednoczesnych_rez: optionalNumber(draft.max_jednoczesnych_rez),
    max_jednoczesnych_osob: optionalNumber(draft.max_jednoczesnych_osob),
    bufor_min: optionalNumber(draft.bufor_min),
    okno_wyprzedzenia_dni: optionalNumber(draft.okno_wyprzedzenia_dni),
    cutoff_min: optionalNumber(draft.cutoff_min),
    min_grupa: optionalPositiveNumber(draft.min_grupa),
    max_grupa: optionalNumber(draft.max_grupa),
    duza_grupa_od: largePartyFrom,
    duza_grupa_tryb: largePartyFrom == null ? null : draft.duza_grupa_tryb,
  }
}

const roomAvailabilityFrom = (row = {}) => ({
  online_aktywna: row.online_aktywna !== false,
  wewnetrzna_aktywna: row.wewnetrzna_aktywna !== false,
  limit_jednoczesnych_rez: row.limit_jednoczesnych_rez ?? '',
  limit_jednoczesnych_osob: row.limit_jednoczesnych_osob ?? '',
  domyslny_bufor_min: row.domyslny_bufor_min ?? '',
})

const roomAvailabilityPayload = (draft) => ({
  online_aktywna: Boolean(draft.online_aktywna),
  wewnetrzna_aktywna: Boolean(draft.wewnetrzna_aktywna),
  limit_jednoczesnych_rez: optionalNumber(draft.limit_jednoczesnych_rez),
  limit_jednoczesnych_osob: optionalNumber(draft.limit_jednoczesnych_osob),
  domyslny_bufor_min: optionalNumber(draft.domyslny_bufor_min),
})

const emptyException = () => ({
  data: localDateIso(),
  typ: 'blackout',
  nazwa: '',
  godz_od: '12:00',
  godz_do: '22:00',
  ostatni_zasiadek: '20:30',
  krok_slotu_min: 15,
  domyslny_turn_time_min: 120,
})

const exceptionFrom = (row = {}) => ({
  data: row.data || localDateIso(),
  typ: row.typ || 'blackout',
  nazwa: row.nazwa || '',
  godz_od: toTime(row.godz_od, '12:00'),
  godz_do: toTime(row.godz_do, '22:00'),
  ostatni_zasiadek: toTime(row.ostatni_zasiadek, '20:30'),
  krok_slotu_min: Math.max(1, toNumber(row.krok_slotu_min ?? row.dlugosc_slotu_min, 15)),
  domyslny_turn_time_min: Math.max(1, toNumber(row.domyslny_turn_time_min ?? row.dlugosc_slotu_min, 120)),
})

const editorDirty = (editor) => Boolean(editor)
  && JSON.stringify(editor.draft) !== JSON.stringify(editor.initial)

const scopeLabel = (scope, rooms = []) => {
  if (!scope) return 'Reguła ogólna'
  const roomId = scope.sala_id ?? scope.room_id
  const room = rooms.find((item) => Number(item.id) === Number(roomId))
  const channel = scope.kanal === 'online' ? 'online' : scope.kanal === 'wewnetrzna' ? 'telefon / obsługa' : null
  return [room ? room.nazwa : roomId ? `Sala #${roomId}` : null, channel].filter(Boolean).join(' · ') || 'Reguła ogólna'
}

const ruleCountLabel = (count) => {
  if (count === 1) return '1 reguła'
  const lastTwo = count % 100
  const last = count % 10
  return `${count} ${last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'reguły' : 'reguł'}`
}

const simulationTitle = ({ allowed, overrideRequired, count }) => {
  if (allowed) return 'Reguły pozwalają przyjąć rezerwację'
  if (overrideRequired) {
    return `Wymaga decyzji obsługi — ${count === 1 ? 'przekroczona' : 'przekroczone'} ${ruleCountLabel(count)}`
  }
  return `Rezerwację ${count === 1 ? 'blokuje' : 'blokują'} ${ruleCountLabel(count)}`
}

function Field({ label, hint, children, wide = false }) {
  return (
    <label className={`field-label min-w-0 ${wide ? 'sm:col-span-2' : ''}`}>
      {label}
      {children}
      {hint ? <span className="mt-1.5 block text-xs font-normal normal-case leading-relaxed tracking-normal text-muted">{hint}</span> : null}
    </label>
  )
}

function Toggle({ checked, onChange, label, disabled = false }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-xl outline-none transition active:scale-[0.98] disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-mint/70"
    >
      <span aria-hidden="true" className={`relative h-6 w-11 rounded-full transition-colors ${checked ? 'bg-mint' : 'bg-white/10'}`}>
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-bg shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
      </span>
    </button>
  )
}

function ServiceEditor({ editor, busy, onChange, onCancel, onSave }) {
  const draft = editor.draft
  const update = (patch) => onChange({ ...editor, draft: { ...draft, ...patch } })
  const toggleDay = (day) => update({
    days: draft.days.includes(day)
      ? draft.days.filter((value) => value !== day)
      : [...draft.days, day].sort(),
  })

  return (
    <form onSubmit={(event) => { event.preventDefault(); onSave() }} className="mt-4 border-t border-line pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-semibold text-ink">{editor.id ? 'Edytuj serwis' : 'Nowy serwis'}</h4>
          <p className="mt-1 text-sm text-muted">Serwis to pora, w której przyjmujesz rezerwacje, np. Lunch albo Kolacja.</p>
        </div>
        <Button variant="subtle" size="sm" onClick={onCancel} disabled={Boolean(busy)}>Anuluj</Button>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Nazwa serwisu" wide>
          <input value={draft.nazwa} onChange={(event) => update({ nazwa: event.target.value })} className="field mt-1.5 min-h-11" maxLength={40} disabled={Boolean(busy)} />
        </Field>
        <fieldset className="sm:col-span-2">
          <legend className="field-label">Dni</legend>
          <div className="mt-2 grid grid-cols-4 gap-2 sm:grid-cols-7">
            {DAYS.map((day, index) => {
              const selected = draft.days.includes(index)
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={selected}
                  aria-label={day}
                  onClick={() => toggleDay(index)}
                  disabled={Boolean(busy) || Boolean(editor.id)}
                  className={`min-h-11 rounded-xl border px-2 text-sm font-semibold transition active:scale-[0.98] disabled:opacity-60 ${selected ? 'border-mint/40 bg-mint/15 text-mint' : 'border-line bg-white/[0.025] text-muted hover:text-ink'}`}
                >
                  {DAY_SHORT[index]}
                </button>
              )
            })}
          </div>
          {editor.id ? <p className="mt-1.5 text-xs text-muted">Aby przenieść serwis na inny dzień, utwórz nowy i usuń ten wpis.</p> : null}
        </fieldset>
        <Field label="Od">
          <input type="time" value={draft.godz_od} onChange={(event) => update({ godz_od: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} required />
        </Field>
        <Field label="Do">
          <input type="time" value={draft.godz_do} onChange={(event) => update({ godz_do: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} required />
        </Field>
        <Field label="Nowy termin co" hint="Krok listy godzin widocznej dla obsługi i gościa.">
          <select value={draft.krok_slotu_min} onChange={(event) => update({ krok_slotu_min: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}>
            {[10, 15, 20, 30, 60].map((value) => <option key={value} value={value}>{value} min</option>)}
          </select>
        </Field>
        <Field label="Typowy czas wizyty">
          <select value={draft.domyslny_turn_time_min} onChange={(event) => update({ domyslny_turn_time_min: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}>
            {[60, 75, 90, 105, 120, 150, 180, 240].map((value) => <option key={value} value={value}>{value} min</option>)}
          </select>
        </Field>
      </div>

      <details className="group mt-5 border-t border-line pt-2">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-2 text-sm font-semibold text-muted outline-none transition hover:bg-white/[0.03] hover:text-ink focus-visible:ring-2 focus-visible:ring-mint/70 [&::-webkit-details-marker]:hidden">
          Dokładniejsze limity tego serwisu
          <Icon name="chevronDown" className="h-4 w-4 transition-transform group-open:rotate-180" />
        </summary>
        <div className="grid grid-cols-1 gap-4 px-2 pb-2 pt-4 sm:grid-cols-2">
          <Field label="Ostatni możliwy start">
            <input type="time" value={draft.ostatni_zasiadek} onChange={(event) => update({ ostatni_zasiadek: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} />
          </Field>
          <Field label="Okno limitów">
            <select value={draft.pacing_okno_min} onChange={(event) => update({ pacing_okno_min: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}>
              {[15, 30, 45, 60, 90, 120].map((value) => <option key={value} value={value}>{value} min</option>)}
            </select>
          </Field>
          <Field label="Wizyta: 1–2 osoby"><input type="number" min="15" step="5" value={draft.turn_2} onChange={(event) => update({ turn_2: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Wizyta: 3–4 osoby"><input type="number" min="15" step="5" value={draft.turn_4} onChange={(event) => update({ turn_4: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Wizyta: 5+ osób"><input type="number" min="15" step="5" value={draft.turn_large} onChange={(event) => update({ turn_large: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Maks. nowych rezerwacji"><input type="number" min="0" value={draft.pacing_max_rez} onChange={(event) => update({ pacing_max_rez: event.target.value })} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Maks. nowych osób"><input type="number" min="0" value={draft.pacing_max_osob} onChange={(event) => update({ pacing_max_osob: event.target.value })} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Maks. rezerwacji jednocześnie"><input type="number" min="0" value={draft.max_jednoczesnych_rez} onChange={(event) => update({ max_jednoczesnych_rez: event.target.value })} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Maks. osób jednocześnie"><input type="number" min="0" value={draft.max_jednoczesnych_osob} onChange={(event) => update({ max_jednoczesnych_osob: event.target.value })} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Duża grupa od" hint="Zostaw puste, jeśli ten serwis nie wymaga osobnej ścieżki dla dużych grup.">
            <input type="number" min="1" value={draft.duza_grupa_od} onChange={(event) => update({ duza_grupa_od: event.target.value })} placeholder="Bez osobnej reguły" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} />
          </Field>
          <Field label="Obsługa dużych grup" hint={draft.duza_grupa_od === '' ? 'Najpierw ustaw próg liczby osób.' : 'Wybierz, co zobaczy gość po przekroczeniu progu.'}>
            <select value={draft.duza_grupa_tryb} onChange={(event) => update({ duza_grupa_tryb: event.target.value })} className="field mt-1.5 min-h-11" disabled={Boolean(busy) || draft.duza_grupa_od === ''}>
              <option value="online">Przyjmuj online automatycznie</option>
              <option value="do_zatwierdzenia">Przyjmij do zatwierdzenia</option>
              <option value="telefon">Poproś o kontakt telefoniczny</option>
            </select>
          </Field>
        </div>
      </details>

      <div className="mt-5 flex justify-end">
        <Button type="submit" variant="ghost" size="sm" loading={busy === 'service'} loadingLabel="Zapisuję serwis…" disabled={!draft.nazwa.trim() || !draft.days.length || !draft.godz_od || !draft.godz_do || (Boolean(editor.id) && !editorDirty(editor)) || Boolean(busy)}>
          <Icon name="check" className="h-4 w-4" /> Zapisz serwis
        </Button>
      </div>
    </form>
  )
}

export default function ReservationAvailability({ active = true } = {}) {
  const { confirm } = useToast()
  const [data, setData] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [policyInitial, setPolicyInitial] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [busy, setBusy] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [serviceEditor, setServiceEditor] = useState(null)
  const [overrideEditor, setOverrideEditor] = useState(null)
  const [roomEditor, setRoomEditor] = useState(null)
  const [exceptionEditor, setExceptionEditor] = useState(null)
  const [simulator, setSimulator] = useState({ data: localDateIso(), godz_od: '18:00', liczba_osob: 2, kanal: 'wewnetrzna', sala_id: '' })
  const [simulation, setSimulation] = useState(null)
  const [simulationError, setSimulationError] = useState(null)
  const readControllerRef = useRef(null)
  const mutationControllerRef = useRef(null)
  const policyDirty = Boolean(policy && policyInitial && JSON.stringify(policy) !== JSON.stringify(policyInitial))
  const dirty = policyDirty || editorDirty(serviceEditor) || editorDirty(overrideEditor) || editorDirty(roomEditor) || editorDirty(exceptionEditor)
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty

  const install = useCallback((payload, { preservePolicyDraft = false } = {}) => {
    const next = {
      polityka: payload.polityka || {},
      serwisy: payload.serwisy || payload.godziny || [],
      nadpisania: payload.nadpisania || [],
      wyjatki: payload.wyjatki || [],
      sale: payload.sale || [],
    }
    setData(next)
    const nextPolicy = policyFrom(next.polityka)
    setPolicyInitial(nextPolicy)
    if (!preservePolicyDraft) setPolicy(nextPolicy)
  }, [])

  const load = useCallback(async ({ retain = false, preservePolicyDraft = dirtyRef.current } = {}) => {
    readControllerRef.current?.abort()
    const controller = new AbortController()
    readControllerRef.current = controller
    if (!retain || !data) setLoading(true)
    else setRefreshing(true)
    setLoadError(null)
    try {
      const payload = await api('/rezerwacje/reguly', 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted) return
      install(payload, { preservePolicyDraft })
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      setLoadError(error.message || 'Nie udało się pobrać reguł rezerwacji.')
    } finally {
      if (readControllerRef.current === controller) readControllerRef.current = null
      if (!controller.signal.aborted) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [data, install])

  useEffect(() => {
    if (active && !data) void load()
  }, [active, data, load])

  useEffect(() => {
    if (!dirty) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  useEffect(() => {
    if (!dirty) return undefined
    return registerReservationLeaveGuard(() => confirm(
      'Wyjść z ustawień dostępności i odrzucić niezapisane zmiany?',
      { title: 'Niezapisane ustawienia', confirmText: 'Wyjdź bez zapisu', cancelText: 'Zostań tutaj' },
    ))
  }, [confirm, dirty])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    readControllerRef.current?.abort()
    mutationControllerRef.current?.abort()
    readControllerRef.current = null
    mutationControllerRef.current = null
    setData(null)
    setPolicy(null)
    setPolicyInitial(null)
    setServiceEditor(null)
    setOverrideEditor(null)
    setRoomEditor(null)
    setExceptionEditor(null)
    setSimulation(null)
    setFeedback(null)
  }), [])

  useEffect(() => () => {
    readControllerRef.current?.abort()
    mutationControllerRef.current?.abort()
  }, [])

  const mutate = async (kind, operation, successMessage) => {
    if (busy) return false
    mutationControllerRef.current?.abort()
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy(kind)
    setFeedback(null)
    try {
      await operation(controller.signal)
      if (controller.signal.aborted) return false
      setFeedback({ type: 'success', message: successMessage })
      // Zapis innej sekcji nie może po cichu wyczyścić szkicu zasad ogólnych.
      await load({ retain: true, preservePolicyDraft: kind !== 'policy' })
      return true
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return false
      setFeedback({ type: 'error', message: error.message || 'Nie udało się zapisać ustawień.' })
      return false
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const savePolicy = async () => {
    const payload = policyPayload(policy)
    if (payload.max_grupa_online !== 0 && payload.max_grupa_online < payload.min_grupa_online) {
      setFeedback({ type: 'error', message: 'Największa grupa online nie może być mniejsza od najmniejszej.' })
      return
    }
    const saved = await mutate('policy', (signal) => api(
      '/rezerwacje/reguly/polityka',
      'PUT',
      payload,
      { signal },
    ), 'Zasady ogólne zostały zapisane.')
    if (saved) setPolicyInitial(policyFrom(policy))
  }

  const saveService = async () => {
    const editor = serviceEditor
    if (!editor || !editor.draft.days.length) return
    const saved = await mutate('service', async (signal) => {
      if (editor.id) {
        return api(`/godziny-otwarcia/${editor.id}`, 'PUT', servicePayload(editor.draft, editor.draft.days[0]), { signal })
      }
      for (const day of editor.draft.days) {
        await api('/godziny-otwarcia', 'POST', servicePayload(editor.draft, day), { signal })
      }
      return null
    }, 'Serwis został zapisany.')
    if (saved) setServiceEditor(null)
  }

  const deleteService = async (row) => {
    const lastActive = data.serwisy.filter((item) => item.aktywny !== false).length <= 1 && row.aktywny !== false
    const approved = await confirm(
      lastActive
        ? 'Usunięcie ostatniego aktywnego serwisu zatrzyma sprzedaż online. Usunąć mimo to?'
        : `Usunąć serwis „${row.nazwa || 'Bez nazwy'}” z dnia ${DAYS[row.dzien_tygodnia]}?`,
      { title: lastActive ? 'Sprzedaż online zostanie zatrzymana' : 'Usuń serwis', confirmText: 'Usuń serwis', cancelText: 'Zostaw' },
    )
    if (!approved) return
    await mutate('service-delete', (signal) => api(`/godziny-otwarcia/${row.id}`, 'DELETE', null, { signal }), 'Serwis został usunięty.')
  }

  const saveOverride = async () => {
    const editor = overrideEditor
    if (!editor) return
    const payload = overridePayload(editor.draft)
    const hasLimit = [
      'pacing_max_rez', 'pacing_max_osob', 'max_jednoczesnych_rez', 'max_jednoczesnych_osob',
      'bufor_min', 'okno_wyprzedzenia_dni', 'cutoff_min', 'min_grupa', 'max_grupa', 'duza_grupa_od',
    ]
      .some((key) => payload[key] != null)
    if (!hasLimit) {
      setFeedback({ type: 'error', message: 'Ustaw przynajmniej jeden limit dla nadpisania.' })
      return
    }
    if (payload.min_grupa != null && payload.max_grupa != null && payload.max_grupa !== 0 && payload.max_grupa < payload.min_grupa) {
      setFeedback({ type: 'error', message: 'Największa grupa nie może być mniejsza od najmniejszej.' })
      return
    }
    const saved = await mutate('override', (signal) => api(
      editor.id ? `/nadpisania-regul-rezerwacji/${editor.id}` : '/nadpisania-regul-rezerwacji',
      editor.id ? 'PUT' : 'POST',
      payload,
      { signal },
    ), 'Limit dla sali lub kanału został zapisany.')
    if (saved) setOverrideEditor(null)
  }

  const deleteOverride = async (row) => {
    const approved = await confirm('Usunąć to nadpisanie i wrócić do zasad ogólnych?', { title: 'Przywróć zasady ogólne', confirmText: 'Usuń nadpisanie', cancelText: 'Zostaw' })
    if (!approved) return
    await mutate('override-delete', (signal) => api(`/nadpisania-regul-rezerwacji/${row.id}`, 'DELETE', null, { signal }), 'Przywrócono zasady ogólne.')
  }

  const saveRoomAvailability = async () => {
    const editor = roomEditor
    if (!editor) return
    const disablesLastOnlineRoom = editor.initial.online_aktywna !== false
      && editor.draft.online_aktywna === false
      && data.sale.every((room) => (
        Number(room.id) === Number(editor.id)
        || room.aktywna === false
        || room.online_aktywna === false
      ))
    if (disablesLastOnlineRoom) {
      const approved = await confirm(
        'To ostatnia aktywna sala dostępna online. Po zapisie goście nie zobaczą wolnych terminów. Wyłączyć ją mimo to?',
        { title: 'Rezerwacje online zostaną zatrzymane', confirmText: 'Wyłącz salę online', cancelText: 'Zostaw włączoną' },
      )
      if (!approved) return
    }
    const saved = await mutate('room', (signal) => api(
      `/rezerwacje/reguly/sale/${editor.id}`,
      'PUT',
      roomAvailabilityPayload(editor.draft),
      { signal },
    ), `Dostępność sali „${editor.name}” została zapisana.`)
    if (saved) setRoomEditor(null)
  }

  const saveException = async () => {
    const editor = exceptionEditor
    if (!editor) return
    const draft = editor.draft
    const payload = {
      data: draft.data,
      typ: draft.typ,
      nazwa: draft.nazwa.trim() || null,
      godz_od: draft.typ === 'godziny_specjalne' ? draft.godz_od : null,
      godz_do: draft.typ === 'godziny_specjalne' ? draft.godz_do : null,
      ostatni_zasiadek: draft.typ === 'godziny_specjalne' ? draft.ostatni_zasiadek || null : null,
      krok_slotu_min: draft.typ === 'godziny_specjalne' ? optionalNumber(draft.krok_slotu_min) : null,
      domyslny_turn_time_min: draft.typ === 'godziny_specjalne' ? optionalNumber(draft.domyslny_turn_time_min) : null,
    }
    const saved = await mutate('exception', (signal) => api(
      editor.id ? `/wyjatki-kalendarza/${editor.id}` : '/wyjatki-kalendarza',
      editor.id ? 'PUT' : 'POST',
      payload,
      { signal },
    ), 'Wyjątek kalendarza został zapisany.')
    if (saved) setExceptionEditor(null)
  }

  const deleteException = async (row) => {
    const approved = await confirm(`Usunąć wyjątek z dnia ${row.data}?`, { title: 'Usuń wyjątek', confirmText: 'Usuń wyjątek', cancelText: 'Zostaw' })
    if (!approved) return
    await mutate('exception-delete', (signal) => api(`/wyjatki-kalendarza/${row.id}`, 'DELETE', null, { signal }), 'Wyjątek został usunięty.')
  }

  const runSimulation = async (event) => {
    event.preventDefault()
    if (busy) return
    mutationControllerRef.current?.abort()
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('simulation')
    setSimulation(null)
    setSimulationError(null)
    try {
      const result = await api('/rezerwacje/reguly/symuluj', 'POST', {
        data: simulator.data,
        godz_od: simulator.godz_od,
        liczba_osob: Math.max(1, Math.round(toNumber(simulator.liczba_osob, 1))),
        kanal: simulator.kanal,
        sala_id: simulator.sala_id === '' ? null : Number(simulator.sala_id),
      }, { signal: controller.signal })
      if (!controller.signal.aborted) setSimulation(result)
    } catch (error) {
      if (!controller.signal.aborted && error?.name !== 'AbortError') setSimulationError(error.message || 'Nie udało się sprawdzić dostępności.')
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const updateSimulator = (patch) => {
    setSimulator((current) => ({ ...current, ...patch }))
    setSimulation(null)
    setSimulationError(null)
  }

  const sortedServices = useMemo(() => [...(data?.serwisy || [])].sort((a, b) => (
    Number(a.dzien_tygodnia) - Number(b.dzien_tygodnia)
    || String(a.godz_od).localeCompare(String(b.godz_od))
  )), [data?.serwisy])
  const violations = simulation?.violations || simulation?.availability?.violations || []
  const checks = simulation?.checks || simulation?.availability?.checks || []
  const simulationAllowed = simulation ? Boolean(simulation.available ?? simulation.decision === 'allow') : null
  const simulationOverrideRequired = simulation?.decision === 'override_required' || simulation?.can_override === true
  const simulationIssueCount = Math.max(violations.length, 1)
  const simulationDetails = violations.length ? violations : checks

  if (loading && !data) {
    return (
      <div className="rounded-2xl border border-line bg-white/[0.02] px-6 py-16 text-center" role="status" aria-label="Wczytywanie reguł dostępności">
        <Spinner className="mx-auto h-6 w-6 text-muted" />
        <p className="mt-3 text-sm text-muted">Wczytuję serwisy i limity…</p>
      </div>
    )
  }

  if (!data) {
    return (
      <Banner variant="danger">
        <div role="alert" className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <span>{loadError || 'Nie udało się wczytać reguł dostępności.'}</span>
          <Button variant="ghost" size="sm" onClick={() => load()}>Spróbuj ponownie</Button>
        </div>
      </Banner>
    )
  }

  return (
    <div className="space-y-6">
      {feedback ? (
        <Banner variant={feedback.type === 'error' ? 'danger' : 'success'}>
          <div role={feedback.type === 'error' ? 'alert' : 'status'} className="flex flex-wrap items-center gap-3">
            <span>{feedback.message}</span>
            {feedback.type === 'error' ? <Button variant="ghost" size="sm" onClick={() => setFeedback(null)}>Zamknij</Button> : null}
          </div>
        </Banner>
      ) : null}
      {loadError && data ? <Banner variant="warn"><span role="alert">Nie udało się odświeżyć reguł. Nadal pokazujemy ostatnio wczytane ustawienia.</span></Banner> : null}

      <section className="rounded-2xl border border-line bg-white/[0.02] p-5 sm:p-6" aria-labelledby="availability-simple-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 id="availability-simple-heading" className="font-display text-lg font-semibold text-ink">Najważniejsze zasady</h3>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Te ustawienia wystarczą większości lokali. Szczegółowe limity znajdziesz niżej.</p>
          </div>
          <span className="text-xs font-medium text-muted" role="status">{refreshing ? 'Odświeżam…' : policyDirty ? 'Niezapisane zmiany' : 'Aktualne'}</span>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Rezerwacje z wyprzedzeniem" hint="Jak daleko w przyszłość można wybrać termin.">
            <div className="relative mt-1.5"><input type="number" min="0" value={policy.okno_wyprzedzenia_dni} onChange={(event) => setPolicy((current) => ({ ...current, okno_wyprzedzenia_dni: event.target.value }))} className="field min-h-11 pr-14" disabled={Boolean(busy)} /><span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted">dni</span></div>
          </Field>
          <Field label="Zamknij rezerwacje online przed terminem" hint="Ile minut przed terminem przestać przyjmować zapisy online.">
            <div className="relative mt-1.5"><input type="number" min="0" value={policy.cutoff_min} onChange={(event) => setPolicy((current) => ({ ...current, cutoff_min: event.target.value }))} className="field min-h-11 pr-14" disabled={Boolean(busy)} /><span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted">min</span></div>
          </Field>
          <Field label="Przerwa między wizytami" hint="Domyślny bufor na przygotowanie stołu.">
            <div className="relative mt-1.5"><input type="number" min="0" value={policy.bufor_min} onChange={(event) => setPolicy((current) => ({ ...current, bufor_min: event.target.value }))} className="field min-h-11 pr-14" disabled={Boolean(busy)} /><span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted">min</span></div>
          </Field>
          <Field label="Najmniejsza grupa online"><input type="number" min="1" value={policy.min_grupa_online} onChange={(event) => setPolicy((current) => ({ ...current, min_grupa_online: event.target.value }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
          <Field label="Największa grupa online" hint="0 oznacza brak limitu. Większą grupę obsługa nadal może dodać ręcznie."><input type="number" min="0" value={policy.max_grupa_online} onChange={(event) => setPolicy((current) => ({ ...current, max_grupa_online: event.target.value }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
        </div>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="subtle" size="sm" onClick={() => setPolicy(policyInitial)} disabled={!policyDirty || Boolean(busy)}>Przywróć</Button>
          <Button size="sm" onClick={savePolicy} loading={busy === 'policy'} loadingLabel="Zapisuję zasady…" disabled={!policyDirty || Boolean(busy)}>Zapisz zasady</Button>
        </div>
      </section>

      <section className="rounded-2xl border border-line bg-white/[0.02] p-5 sm:p-6" aria-labelledby="services-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 id="services-heading" className="font-display text-lg font-semibold text-ink">Serwisy</h3>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Określ, kiedy przyjmujesz gości i jak długo zwykle zajmują stolik.</p>
          </div>
          {!serviceEditor ? <Button variant="ghost" size="sm" onClick={() => { const draft = emptyService(); setServiceEditor({ id: null, draft, initial: draft }) }} disabled={Boolean(busy)}><Icon name="plus" className="h-4 w-4" /> Dodaj serwis</Button> : null}
        </div>

        <div className="mt-5 divide-y divide-line border-y border-line">
          {!sortedServices.length ? <p className="py-6 text-sm text-muted">Nie ma jeszcze serwisów. Dodaj Lunch, Kolację albo własną porę rezerwacji.</p> : null}
          {sortedServices.map((row) => (
            <div key={row.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="break-words font-semibold text-ink">{row.nazwa || 'Serwis'} <span className="font-normal text-muted">· {DAYS[row.dzien_tygodnia]}</span></p>
                <p className="mt-1 break-words text-sm text-muted">{toTime(row.godz_od)}–{toTime(row.godz_do)} · co {row.krok_slotu_min ?? row.dlugosc_slotu_min ?? 15} min · wizyta {row.domyslny_turn_time_min ?? row.dlugosc_slotu_min ?? 120} min</p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="subtle" size="sm" onClick={() => { const draft = serviceFrom(row); setServiceEditor({ id: row.id, draft, initial: draft }) }} disabled={Boolean(busy)}>Edytuj</Button>
                <Button variant="subtle" size="sm" onClick={() => deleteService(row)} disabled={Boolean(busy)} aria-label={`Usuń serwis ${row.nazwa || ''}, ${DAYS[row.dzien_tygodnia]}`} className="text-danger hover:bg-danger/10"><Icon name="trash" className="h-4 w-4" /></Button>
              </div>
            </div>
          ))}
        </div>
        {serviceEditor ? <ServiceEditor editor={serviceEditor} busy={busy} onChange={setServiceEditor} onCancel={() => setServiceEditor(null)} onSave={saveService} /> : null}
      </section>

      <details className="group rounded-2xl border border-line bg-white/[0.02]">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 outline-none focus-visible:ring-2 focus-visible:ring-mint/70 sm:px-6 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block break-words font-display text-lg font-semibold text-ink">Ustawienia zaawansowane</span>
            <span className="mt-1 block break-words text-sm font-normal text-muted">Sale i kanały · {data.nadpisania.length} {data.nadpisania.length === 1 ? 'własna reguła' : 'własnych reguł'}</span>
          </span>
          <Icon name="chevronDown" className="h-5 w-5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-line px-5 pb-6 pt-5 sm:px-6">
          <section aria-labelledby="room-availability-heading">
            <div>
              <h4 id="room-availability-heading" className="text-base font-semibold text-ink">Dostępność sal</h4>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Zdecyduj, z których sal może korzystać rezerwacja online i obsługa. Limity sali mają pierwszeństwo przed zasadami ogólnymi.</p>
            </div>
            <div className="mt-4 divide-y divide-line border-y border-line">
              {!data.sale.length ? <p className="py-5 text-sm text-muted">Najpierw dodaj salę w konfiguracji planu sali.</p> : null}
              {data.sale.map((room) => {
                const editing = roomEditor?.id === room.id
                return (
                  <div key={room.id} className="py-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-semibold text-ink">{room.nazwa}</p>
                        <p className="mt-1 text-xs leading-relaxed text-muted">
                          Online: {room.online_aktywna === false ? 'wyłączona' : 'włączona'} · obsługa: {room.wewnetrzna_aktywna === false ? 'wyłączona' : 'włączona'}
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-muted">
                          Jednocześnie: {room.limit_jednoczesnych_rez ?? 'bez limitu'} rez. · {room.limit_jednoczesnych_osob ?? 'bez limitu'} os. · bufor {room.domyslny_bufor_min ?? 'ogólny'}{room.domyslny_bufor_min == null ? '' : ' min'}
                        </p>
                      </div>
                      {!editing ? (
                        <Button
                          variant="subtle"
                          size="sm"
                          aria-label={`Dostosuj dostępność sali ${room.nazwa}`}
                          onClick={() => {
                            const draft = roomAvailabilityFrom(room)
                            setRoomEditor({ id: room.id, name: room.nazwa, draft, initial: draft })
                          }}
                          disabled={Boolean(busy) || Boolean(roomEditor)}
                        >
                          Dostosuj
                        </Button>
                      ) : null}
                    </div>
                    {editing ? (
                      <form onSubmit={(event) => { event.preventDefault(); saveRoomAvailability() }} className="mt-4 border-t border-line pt-4">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <div className="flex min-h-14 items-center justify-between gap-4 rounded-xl bg-white/[0.025] px-3 py-2">
                            <div>
                              <p className="text-sm font-medium text-ink">Rezerwacje online</p>
                              <p className="mt-0.5 text-xs text-muted">Goście mogą wybrać tę salę.</p>
                            </div>
                            <Toggle checked={roomEditor.draft.online_aktywna} onChange={(value) => setRoomEditor((current) => ({ ...current, draft: { ...current.draft, online_aktywna: value } }))} label={`Rezerwacje online w sali ${room.nazwa}`} disabled={Boolean(busy)} />
                          </div>
                          <div className="flex min-h-14 items-center justify-between gap-4 rounded-xl bg-white/[0.025] px-3 py-2">
                            <div>
                              <p className="text-sm font-medium text-ink">Telefon i obsługa</p>
                              <p className="mt-0.5 text-xs text-muted">Recepcja może przypisywać tę salę.</p>
                            </div>
                            <Toggle checked={roomEditor.draft.wewnetrzna_aktywna} onChange={(value) => setRoomEditor((current) => ({ ...current, draft: { ...current.draft, wewnetrzna_aktywna: value } }))} label={`Rezerwacje obsługi w sali ${room.nazwa}`} disabled={Boolean(busy)} />
                          </div>
                        </div>
                        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
                          <Field label="Maks. rezerwacji w sali"><input type="number" min="0" value={roomEditor.draft.limit_jednoczesnych_rez} onChange={(event) => setRoomEditor((current) => ({ ...current, draft: { ...current.draft, limit_jednoczesnych_rez: event.target.value } }))} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                          <Field label="Maks. osób w sali"><input type="number" min="0" value={roomEditor.draft.limit_jednoczesnych_osob} onChange={(event) => setRoomEditor((current) => ({ ...current, draft: { ...current.draft, limit_jednoczesnych_osob: event.target.value } }))} placeholder="Bez limitu" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                          <Field label="Bufor sali" hint="Puste = bufor ogólny."><input type="number" min="0" value={roomEditor.draft.domyslny_bufor_min} onChange={(event) => setRoomEditor((current) => ({ ...current, draft: { ...current.draft, domyslny_bufor_min: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                        </div>
                        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                          <Button variant="subtle" size="sm" onClick={() => setRoomEditor(null)} disabled={Boolean(busy)}>Anuluj</Button>
                          <Button type="submit" variant="ghost" size="sm" loading={busy === 'room'} loadingLabel="Zapisuję salę…" disabled={!editorDirty(roomEditor) || Boolean(busy)}>Zapisz dostępność sali</Button>
                        </div>
                      </form>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </section>

          <section className="mt-7 border-t border-line pt-6" aria-labelledby="custom-rules-heading">
            <div>
              <h4 id="custom-rules-heading" className="text-base font-semibold text-ink">Własne reguły zakresu</h4>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Dodawaj tylko różnice względem serwisu. Puste pola nadal korzystają z zasad ogólnych.</p>
            </div>
            <div className="mt-4 divide-y divide-line border-y border-line">
            {!data.nadpisania.length ? <p className="py-5 text-sm text-muted">Wszystkie sale i kanały korzystają z zasad ogólnych.</p> : null}
            {data.nadpisania.map((row) => (
              <div key={row.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="break-words text-sm font-semibold text-ink">{scopeLabel(row, data.sale)}</p>
                  <p className="mt-1 break-words text-xs text-muted">Rezerwacje: {row.pacing_max_rez ?? 'bez limitu'} · osoby: {row.pacing_max_osob ?? 'bez limitu'} · okno {row.pacing_okno_min == null ? 'dziedziczone' : `${row.pacing_okno_min} min`}</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="subtle" size="sm" onClick={() => { const draft = overrideFrom(row); setOverrideEditor({ id: row.id, draft, initial: draft }) }} disabled={Boolean(busy)}>Edytuj</Button>
                  <Button variant="subtle" size="sm" onClick={() => deleteOverride(row)} disabled={Boolean(busy)} className="text-danger hover:bg-danger/10">Usuń</Button>
                </div>
              </div>
            ))}
          </div>
          {!overrideEditor ? <Button variant="ghost" size="sm" onClick={() => { const draft = emptyOverride(); setOverrideEditor({ id: null, draft, initial: draft }) }} disabled={Boolean(busy)} className="mt-4"><Icon name="plus" className="h-4 w-4" /> Dodaj własny limit</Button> : null}
          {overrideEditor ? (
            <form onSubmit={(event) => { event.preventDefault(); saveOverride() }} className="mt-5 border-t border-line pt-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Sala"><select value={overrideEditor.draft.sala_id} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, sala_id: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}><option value="">Wszystkie sale</option>{data.sale.map((room) => <option key={room.id} value={room.id}>{room.nazwa}</option>)}</select></Field>
                <Field label="Kanał"><select value={overrideEditor.draft.kanal} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, kanal: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}><option value="oba">Wszystkie kanały</option><option value="online">Online</option><option value="wewnetrzna">Telefon / obsługa</option></select></Field>
                <Field label="Serwis"><select value={overrideEditor.draft.serwis_id} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, serwis_id: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}><option value="">Każdy serwis</option>{data.serwisy.map((row) => <option key={row.id} value={row.id}>{row.nazwa || 'Serwis'} · {DAY_SHORT[row.dzien_tygodnia]}</option>)}</select></Field>
                <Field label="Okno limitu" hint="Puste = okno z serwisu."><input type="number" min="1" value={overrideEditor.draft.pacing_okno_min} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, pacing_okno_min: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                {[['pacing_max_rez', 'Maks. nowych rezerwacji'], ['pacing_max_osob', 'Maks. nowych osób'], ['max_jednoczesnych_rez', 'Maks. rezerwacji jednocześnie'], ['max_jednoczesnych_osob', 'Maks. osób jednocześnie']].map(([key, label]) => <Field key={key} label={label}><input type="number" min="0" value={overrideEditor.draft[key]} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, [key]: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>)}
              </div>
              <details className="group mt-5 border-t border-line pt-2">
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-2 text-sm font-semibold text-muted outline-none transition hover:bg-white/[0.03] hover:text-ink focus-visible:ring-2 focus-visible:ring-mint/70 [&::-webkit-details-marker]:hidden">
                  Więcej reguł dla tego zakresu
                  <Icon name="chevronDown" className="h-4 w-4 transition-transform group-open:rotate-180" />
                </summary>
                <div className="grid grid-cols-1 gap-4 px-2 pb-2 pt-4 sm:grid-cols-2">
                  <Field label="Bufor między wizytami" hint="Puste = wartość odziedziczona."><input type="number" min="0" value={overrideEditor.draft.bufor_min} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, bufor_min: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Rezerwacje z wyprzedzeniem"><input type="number" min="0" value={overrideEditor.draft.okno_wyprzedzenia_dni} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, okno_wyprzedzenia_dni: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Zamknij rezerwacje przed terminem"><input type="number" min="0" value={overrideEditor.draft.cutoff_min} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, cutoff_min: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Najmniejsza grupa"><input type="number" min="1" value={overrideEditor.draft.min_grupa} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, min_grupa: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Największa grupa" hint="0 oznacza brak limitu."><input type="number" min="0" value={overrideEditor.draft.max_grupa} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, max_grupa: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Duża grupa od"><input type="number" min="1" value={overrideEditor.draft.duza_grupa_od} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, duza_grupa_od: event.target.value } }))} placeholder="Dziedzicz" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
                  <Field label="Obsługa dużych grup" hint={overrideEditor.draft.duza_grupa_od === '' ? 'Najpierw ustaw próg liczby osób.' : null}>
                    <select value={overrideEditor.draft.duza_grupa_tryb} onChange={(event) => setOverrideEditor((current) => ({ ...current, draft: { ...current.draft, duza_grupa_tryb: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy) || overrideEditor.draft.duza_grupa_od === ''}>
                      <option value="online">Przyjmuj online automatycznie</option>
                      <option value="do_zatwierdzenia">Przyjmij do zatwierdzenia</option>
                      <option value="telefon">Poproś o kontakt telefoniczny</option>
                    </select>
                  </Field>
                </div>
              </details>
              <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button variant="subtle" size="sm" onClick={() => setOverrideEditor(null)} disabled={Boolean(busy)}>Anuluj</Button><Button type="submit" variant="ghost" size="sm" loading={busy === 'override'} loadingLabel="Zapisuję limit…" disabled={!editorDirty(overrideEditor) || Boolean(busy)}>Zapisz limit</Button></div>
            </form>
          ) : null}
          </section>
        </div>
      </details>

      <section className="rounded-2xl border border-line bg-white/[0.02] p-5 sm:p-6" aria-labelledby="exceptions-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div><h3 id="exceptions-heading" className="font-display text-lg font-semibold text-ink">Wyjątki</h3><p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Zamknij konkretny dzień albo ustaw w nim inne godziny.</p></div>
          {!exceptionEditor ? <Button variant="ghost" size="sm" onClick={() => { const draft = emptyException(); setExceptionEditor({ id: null, draft, initial: draft }) }} disabled={Boolean(busy)}><Icon name="plus" className="h-4 w-4" /> Dodaj wyjątek</Button> : null}
        </div>
        <div className="mt-5 divide-y divide-line border-y border-line">
          {!data.wyjatki.length ? <p className="py-5 text-sm text-muted">Nie ma nadchodzących wyjątków.</p> : null}
          {data.wyjatki.map((row) => <div key={row.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className="break-words font-semibold text-ink">{row.data} · {row.nazwa || (row.typ === 'blackout' ? 'Zamknięte' : 'Inne godziny')}</p><p className="mt-1 break-words text-sm text-muted">{row.typ === 'blackout' ? 'Bez przyjmowania nowych rezerwacji' : `${toTime(row.godz_od)}–${toTime(row.godz_do)}`}</p></div><div className="flex self-start gap-2 sm:self-auto"><Button variant="subtle" size="sm" onClick={() => { const draft = exceptionFrom(row); setExceptionEditor({ id: row.id, draft, initial: draft }) }} disabled={Boolean(busy)}>Edytuj</Button><Button variant="subtle" size="sm" onClick={() => deleteException(row)} disabled={Boolean(busy)} className="text-danger hover:bg-danger/10">Usuń</Button></div></div>)}
        </div>
        {exceptionEditor ? (
          <form onSubmit={(event) => { event.preventDefault(); saveException() }} className="mt-5 border-t border-line pt-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Dzień"><input type="date" value={exceptionEditor.draft.data} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, data: event.target.value } }))} className="field mt-1.5 min-h-11" required disabled={Boolean(busy)} /></Field>
              <Field label="Co ma się wydarzyć?"><select value={exceptionEditor.draft.typ} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, typ: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)}><option value="blackout">Zamknięte cały dzień</option><option value="godziny_specjalne">Inne godziny</option></select></Field>
              <Field label="Nazwa / powód" wide><input value={exceptionEditor.draft.nazwa} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, nazwa: event.target.value } }))} placeholder="np. Wigilia, remont" className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field>
              {exceptionEditor.draft.typ === 'godziny_specjalne' ? <><Field label="Od"><input type="time" value={exceptionEditor.draft.godz_od} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, godz_od: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field><Field label="Do"><input type="time" value={exceptionEditor.draft.godz_do} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, godz_do: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field><Field label="Ostatni możliwy start"><input type="time" value={exceptionEditor.draft.ostatni_zasiadek} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, ostatni_zasiadek: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field><Field label="Nowy termin co"><input type="number" min="1" value={exceptionEditor.draft.krok_slotu_min} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, krok_slotu_min: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field><Field label="Typowy czas wizyty"><input type="number" min="1" value={exceptionEditor.draft.domyslny_turn_time_min} onChange={(event) => setExceptionEditor((current) => ({ ...current, draft: { ...current.draft, domyslny_turn_time_min: event.target.value } }))} className="field mt-1.5 min-h-11" disabled={Boolean(busy)} /></Field></> : <Banner variant="warn" className="sm:col-span-2">Ten wyjątek zatrzyma sprzedaż online w wybranym dniu.</Banner>}
            </div>
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button variant="subtle" size="sm" onClick={() => setExceptionEditor(null)} disabled={Boolean(busy)}>Anuluj</Button><Button type="submit" variant="ghost" size="sm" loading={busy === 'exception'} loadingLabel="Zapisuję wyjątek…" disabled={!editorDirty(exceptionEditor) || Boolean(busy)}>Zapisz wyjątek</Button></div>
          </form>
        ) : null}
      </section>

      <section className="rounded-2xl border border-line bg-white/[0.02] p-5 sm:p-6" aria-labelledby="simulator-heading">
        <div>
          <h3 id="simulator-heading" className="font-display text-lg font-semibold text-ink">Sprawdź dostępność</h3>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Zobacz decyzję, proponowany przydział i bezpieczne alternatywy dla konkretnej rezerwacji.</p>
        </div>
        <form onSubmit={runSimulation} className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Dzień"><input type="date" value={simulator.data} onChange={(event) => updateSimulator({ data: event.target.value })} className="field mt-1.5 min-h-11" required disabled={busy === 'simulation'} /></Field>
          <Field label="Godzina"><input type="time" value={simulator.godz_od} onChange={(event) => updateSimulator({ godz_od: event.target.value })} className="field mt-1.5 min-h-11" required disabled={busy === 'simulation'} /></Field>
          <Field label="Liczba osób"><input type="number" min="1" value={simulator.liczba_osob} onChange={(event) => updateSimulator({ liczba_osob: event.target.value })} className="field mt-1.5 min-h-11" required disabled={busy === 'simulation'} /></Field>
          <Field label="Kanał"><select value={simulator.kanal} onChange={(event) => updateSimulator({ kanal: event.target.value })} className="field mt-1.5 min-h-11" disabled={busy === 'simulation'}><option value="wewnetrzna">Telefon / obsługa</option><option value="online">Online</option></select></Field>
          <Field label="Sala"><select value={simulator.sala_id} onChange={(event) => updateSimulator({ sala_id: event.target.value })} className="field mt-1.5 min-h-11" disabled={busy === 'simulation'}><option value="">Dowolna sala</option>{data.sale.map((room) => <option key={room.id} value={room.id}>{room.nazwa}</option>)}</select></Field>
          <div className="sm:col-span-2 lg:col-span-5"><Button type="submit" variant="ghost" size="sm" loading={busy === 'simulation'} loadingLabel="Sprawdzam dostępność…" disabled={Boolean(busy) && busy !== 'simulation'}><Icon name="search" className="h-4 w-4" /> Sprawdź dostępność</Button></div>
        </form>

        {simulationError ? <p role="alert" className="mt-4 text-sm text-danger">{simulationError}</p> : null}
        {simulation ? (
          <div className="mt-5 border-t border-line pt-5">
            <div className="flex items-start gap-3" aria-live="polite" aria-atomic="true">
              <Icon name={simulationAllowed ? 'check' : 'warning'} className={`mt-0.5 h-5 w-5 shrink-0 ${simulationAllowed ? 'text-success' : simulationOverrideRequired ? 'text-lemon' : 'text-danger'}`} />
              <div className="min-w-0">
                <p className="break-words font-semibold text-ink">{simulationTitle({ allowed: simulationAllowed, overrideRequired: simulationOverrideRequired, count: simulationIssueCount })}</p>
                {simulation.service ? <p className="mt-1 break-words text-sm text-muted">{simulation.service.name || simulation.service.nazwa || 'Serwis'} · wizyta do {toTime(simulation.visit_end, '—')}</p> : null}
              </div>
            </div>

            {simulation.allocation ? (
              <ReservationAllocationSummary
                className="mt-4"
                allocation={{
                  ...simulation.allocation,
                  visit_end: simulation.allocation.visit_end || simulation.visit_end,
                }}
                alternatives={simulation.alternatives || []}
              />
            ) : null}

            {simulationDetails.length ? (
              <details className={`group ${simulation.allocation ? '' : 'mt-4 border-y border-line'}`} open={!simulationAllowed}>
                <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 py-2 text-sm font-semibold text-muted transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/60 [&::-webkit-details-marker]:hidden">
                  <span>{violations.length ? 'Szczegóły decyzji' : 'Sprawdzone reguły'} · {ruleCountLabel(simulationDetails.length)}</span>
                  <span aria-hidden="true" className="ml-auto text-base leading-none transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none">⌄</span>
                </summary>
                <ul className="divide-y divide-line border-t border-line">{simulationDetails.map((check, index) => <li key={`${check.code || check.rule}-${index}`} className="py-3 text-sm"><div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3"><span className="min-w-0 break-words font-medium text-ink">{check.message || check.rule || 'Sprawdzona reguła'}</span><span className="break-words text-xs text-muted sm:shrink-0 sm:text-right">{scopeLabel(check.scope, data.sale)}</span></div>{check.limit != null ? <p className="mt-1 break-words text-xs text-muted">Limit: {check.limit} · teraz: {check.observed ?? '—'} · po operacji: {check.projected ?? '—'}</p> : null}</li>)}</ul>
              </details>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  )
}
