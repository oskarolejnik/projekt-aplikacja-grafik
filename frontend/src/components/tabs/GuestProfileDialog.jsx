import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { DialogFrame } from '../ui/DialogFrame'
import { useToast } from '../ui/Toast'

const STATUS_LABELS = {
  rezerwacja: 'Nowa',
  potwierdzona: 'Potwierdzona',
  odbyla: 'Odbyła się',
  no_show: 'No-show',
  odwolana: 'Odwołana',
}

const formFromProfile = (data) => {
  const profile = data?.profil || {}
  return {
    nazwisko: profile.nazwisko || data?.nazwisko || '',
    tagi: (profile.tagi || []).join(', '),
    vip: Boolean(profile.vip),
    alergie: profile.alergie || '',
    dieta: profile.dieta || '',
    preferowana_strefa: profile.preferowana_strefa || '',
    notatka: profile.notatka || '',
    okazja_typ: profile.okazja_typ || '',
    okazja_data: profile.okazja_data || '',
  }
}

const formSnapshot = (form) => JSON.stringify(form || null)

const formPayload = (form) => ({
  nazwisko: form.nazwisko.trim() || null,
  tagi: form.tagi.split(',').map((value) => value.trim()).filter(Boolean),
  vip: form.vip,
  alergie: form.alergie.trim() || null,
  dieta: form.dieta.trim() || null,
  preferowana_strefa: form.preferowana_strefa.trim() || null,
  notatka: form.notatka.trim() || null,
  okazja_typ: form.okazja_typ || null,
  okazja_data: form.okazja_data.trim() || null,
})

function ProfileSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Ładowanie karty gościa">
      <div className="flex flex-wrap gap-2">
        {[0, 1, 2].map((item) => <span key={item} className="h-9 w-24 animate-pulse rounded-xl bg-white/[0.06] motion-reduce:animate-none" />)}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {[0, 1, 2, 3].map((item) => <span key={item} className="h-16 animate-pulse rounded-xl bg-white/[0.05] motion-reduce:animate-none" />)}
      </div>
      <span className="sr-only">Ładowanie profilu…</span>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <span className="inline-flex min-h-9 items-baseline gap-1.5 rounded-xl border border-line bg-white/[0.025] px-3 py-2 text-xs">
      <span className="font-display text-base font-semibold tabular-nums text-ink">{value}</span>
      <span className="text-muted">{label}</span>
    </span>
  )
}

function GuestSummary({ data }) {
  const stats = data.statystyki || {}
  const profile = data.profil || {}
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm text-muted">Gość</p>
        <p className="mt-0.5 text-lg font-semibold text-ink">{data.nazwisko || 'Bez nazwiska'}</p>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Statystyki gościa">
        <Metric label="wizyt" value={stats.wizyt ?? 0} />
        <Metric label="odbytych" value={stats.odbyte ?? 0} />
        <Metric label="no-show" value={`${stats.no_show ?? 0}${stats.no_show_proc ? ` · ${stats.no_show_proc}%` : ''}`} />
        {(stats.vip_auto || profile.vip) ? <span className="inline-flex min-h-9 items-center rounded-xl bg-mint/15 px-3 py-2 text-xs font-semibold text-mint">VIP</span> : null}
      </div>
    </div>
  )
}

function ReadOnlyProfile({ data }) {
  const profile = data.profil
  const capabilities = data.capabilities || {}
  const tags = profile?.tagi || []

  if (!profile) {
    return (
      <div className="rounded-xl border border-dashed border-line px-5 py-8 text-center">
        <p className="text-sm font-semibold text-ink">Profil nie został jeszcze uzupełniony</p>
        <p className="mt-1 text-sm text-muted">Historia wizyt pozostaje dostępna poniżej.</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <ReadOnlyField label="Tagi" value={tags.length ? tags.join(', ') : null} />
        <ReadOnlyField label="Preferowana strefa" value={profile.preferowana_strefa} />
        <ReadOnlyField label="Okazja" value={profile.okazja_typ} />
        <ReadOnlyField label="Data okazji" value={profile.okazja_data} />
      </dl>

      {capabilities.can_view_sensitive ? (
        <dl className="grid gap-x-6 gap-y-4 border-t border-line pt-5 sm:grid-cols-2">
          <ReadOnlyField label="Alergie" value={profile.alergie} />
          <ReadOnlyField label="Dieta" value={profile.dieta} />
        </dl>
      ) : (
        <Banner variant="info">Dane wrażliwe są ukryte zgodnie z uprawnieniami konta.</Banner>
      )}

      {capabilities.can_view_internal_notes ? (
        <ReadOnlyField label="Notatka wewnętrzna" value={profile.notatka} multiline />
      ) : (
        <Banner variant="info">Notatka wewnętrzna jest ukryta zgodnie z uprawnieniami konta.</Banner>
      )}
    </div>
  )
}

function ReadOnlyField({ label, value, multiline = false }) {
  return (
    <div className={multiline ? 'min-w-0' : ''}>
      <dt className="text-xs font-semibold text-muted">{label}</dt>
      <dd className={`mt-1 text-sm text-ink ${multiline ? 'whitespace-pre-wrap leading-relaxed' : ''}`}>{value || 'Brak danych'}</dd>
    </div>
  )
}

function ProfileForm({ form, setForm, saving }) {
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }))
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="field-label sm:col-span-2">Nazwisko / nazwa
        <input className="field mt-1.5" value={form.nazwisko} onChange={(event) => update('nazwisko', event.target.value)} disabled={saving} autoComplete="off" />
      </label>
      <label className="field-label sm:col-span-2">Tagi
        <input className="field mt-1.5" value={form.tagi} onChange={(event) => update('tagi', event.target.value)} disabled={saving} placeholder="np. stały, okno, firmowy" autoComplete="off" />
      </label>
      <label className="field-label sm:col-span-2">Alergie · dane wrażliwe
        <input className="field mt-1.5" value={form.alergie} onChange={(event) => update('alergie', event.target.value)} disabled={saving} placeholder="np. orzechy" autoComplete="off" />
      </label>
      <label className="field-label">Dieta
        <input className="field mt-1.5" value={form.dieta} onChange={(event) => update('dieta', event.target.value)} disabled={saving} placeholder="np. wegetariańska" autoComplete="off" />
      </label>
      <label className="field-label">Preferowana strefa
        <input className="field mt-1.5" value={form.preferowana_strefa} onChange={(event) => update('preferowana_strefa', event.target.value)} disabled={saving} placeholder="np. ogród" autoComplete="off" />
      </label>
      <label className="field-label">Okazja
        <select className="field mt-1.5" value={form.okazja_typ} onChange={(event) => update('okazja_typ', event.target.value)} disabled={saving}>
          <option value="">Brak</option>
          <option value="urodziny">Urodziny</option>
          <option value="rocznica">Rocznica</option>
        </select>
      </label>
      <label className="field-label">Data okazji
        <input className="field mt-1.5" value={form.okazja_data} onChange={(event) => update('okazja_data', event.target.value)} disabled={saving} placeholder="MM-DD" inputMode="numeric" autoComplete="off" />
      </label>
      <label className="field-label sm:col-span-2">Notatka wewnętrzna
        <textarea className="field mt-1.5 min-h-24 resize-y" value={form.notatka} onChange={(event) => update('notatka', event.target.value)} disabled={saving} />
      </label>
      <label className="flex min-h-11 items-center gap-3 rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink">
        <input type="checkbox" checked={form.vip} onChange={(event) => update('vip', event.target.checked)} disabled={saving} className="h-4 w-4 accent-mint" />
        VIP oznaczony ręcznie
      </label>
    </div>
  )
}

const CONSENT_STATE = {
  granted: ['Aktywna', 'text-success'],
  withdrawn: ['Wycofana', 'text-danger'],
  declined: ['Nieudzielona', 'text-muted'],
  mixed: ['Wymaga wyjaśnienia', 'text-lemon'],
  legacy_unverified: ['Brak dowodu', 'text-lemon'],
  missing: ['Brak dowodu', 'text-muted'],
}

const CONSENT_SOURCE = {
  public_widget: 'Widget online',
  operator_phone: 'Telefon',
  operator_in_person: 'Osobiście',
  operator_email: 'E-mail',
  import: 'Import',
}

const consentTimeWarsaw = (value) => {
  if (!value) return 'Brak czasu'
  const raw = String(value)
  const normalized = /(?:z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) return 'Nieprawidłowy czas'
  return new Intl.DateTimeFormat('pl-PL', {
    timeZone: 'Europe/Warsaw',
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(parsed)
}

function ConsentHistory({
  consent,
  canManage,
  disabled,
  saving,
  error,
  status,
  onRecord,
}) {
  const [source, setSource] = useState('operator_phone')
  const [label, tone] = CONSENT_STATE[consent?.state] || CONSENT_STATE.missing
  const history = consent?.history || []
  const hasActiveConsent = consent?.active === true || consent?.state === 'granted'
  return (
    <section className="border-y border-line py-5" aria-labelledby="guest-consent-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="guest-consent-title" className="text-sm font-semibold text-ink">Zgoda marketingowa</h3>
          <p className={`mt-1 text-sm font-semibold ${tone}`}>{label}</p>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
            Zgoda ma wersję, źródło i czas pozyskania. Edycja profilu nie może jej włączyć.
          </p>
        </div>
        {consent?.legacy_unverified ? (
          <span className="rounded-full bg-lemon/15 px-2.5 py-1 text-xs font-semibold text-lemon">Starszy wpis bez dowodu</span>
        ) : null}
      </div>

      {history.length ? (
        <ol className="mt-4 divide-y divide-line/70" aria-label="Historia zgody marketingowej">
          {history.slice(0, 5).map((event, index) => (
            <li key={`${event.captured_at || ''}:${event.source || ''}:${index}`} className="grid gap-1 py-2 text-xs sm:grid-cols-[1fr_auto] sm:gap-4">
              <span className="text-ink">
                {event.decision === 'grant' ? 'Udzielona' : event.decision === 'withdraw' ? 'Wycofana' : 'Nieudzielona'}
                <span className="text-muted"> · {CONSENT_SOURCE[event.source] || event.source}</span>
              </span>
              <span className="text-muted">
                {consentTimeWarsaw(event.captured_at)}
                {event.document_version ? ` · ${event.document_version}` : ''}
              </span>
            </li>
          ))}
        </ol>
      ) : <p className="mt-4 text-sm text-muted">Nie zapisano jeszcze wersjonowanego zdarzenia.</p>}

      {canManage ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(10rem,1fr)_auto_auto_auto] sm:items-end">
          <label>
            <span className="field-label">Źródło potwierdzenia</span>
            <select className="field mt-1.5" value={source} onChange={(event) => setSource(event.target.value)} disabled={disabled || saving}>
              <option value="operator_phone">Rozmowa telefoniczna</option>
              <option value="operator_in_person">Osobiście</option>
              <option value="operator_email">Wiadomość e-mail</option>
            </select>
          </label>
          <Button
            type="button"
            variant="subtle"
            disabled={disabled || saving || hasActiveConsent}
            onClick={() => onRecord('decline', source)}
          >
            Zapisz odmowę
          </Button>
          <Button
            type="button"
            variant="subtle"
            disabled={disabled || saving || !hasActiveConsent}
            onClick={() => onRecord('withdraw', source)}
          >
            Wycofaj zgodę
          </Button>
          <Button type="button" disabled={disabled || saving} loading={saving} loadingLabel="Zapisuję zgodę" onClick={() => onRecord('grant', source)}>
            Zapisz zgodę
          </Button>
        </div>
      ) : null}
      {disabled && canManage ? <p className="mt-2 text-xs text-muted">Najpierw zapisz albo odrzuć zmiany profilu.</p> : null}
      {error ? <div className="mt-3" role="alert"><Banner variant="danger">{error}</Banner></div> : null}
      <p className="mt-2 min-h-5 text-xs text-success" role="status" aria-live="polite">{status}</p>
    </section>
  )
}

const finiteMinutes = (value) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed) : null
}

const visitTiming = (visit) => {
  const planned = finiteMinutes(
    visit.planowany_czas_min
      ?? visit.planowany_turn_time_min
      ?? visit.planned_turn_time_min,
  )
  const actual = finiteMinutes(
    visit.rzeczywisty_czas_min
      ?? visit.rzeczywisty_turn_time_min
      ?? visit.actual_turn_time_min,
  )
  const explicitDelta = finiteMinutes(Math.abs(Number(
    visit.odchylenie_min
      ?? visit.odchylenie_czasu_min
      ?? visit.turn_time_delta_min,
  )))
  const delta = actual !== null && planned !== null
    ? actual - planned
    : explicitDelta
  const measurement = visit.pomiar
  const measured = actual !== null && (
    measurement == null
      || measurement === true
      || measurement === 'pelny'
      || measurement === 'complete'
      || measurement?.kompletny === true
      || measurement?.status === 'pelny'
      || measurement?.status === 'complete'
  )
  return { actual: measured ? actual : null, planned, delta: measured ? delta : null }
}

const visitAllocation = (visit) => {
  const allocation = visit.przydzial || visit.allocation || {}
  const room = allocation.sala?.nazwa
    || allocation.sala_nazwa
    || allocation.room?.name
    || allocation.room_name
    || visit.sala_nazwa
    || null
  const combination = allocation.kombinacja?.nazwa
    || allocation.kombinacja_nazwa
    || allocation.combination?.name
    || allocation.combination_name
    || visit.kombinacja_nazwa
    || null
  const rawTables = allocation.stoliki
    || allocation.tables
    || visit.stoliki
    || []
  const tables = rawTables
    .map((table) => typeof table === 'string' ? table : (table?.nazwa || table?.name))
    .filter(Boolean)
  const parts = [
    room,
    combination ? `Konfiguracja: ${combination}` : null,
    tables.length ? `Stoły: ${tables.join(' + ')}` : null,
  ].filter(Boolean)
  return [...new Set(parts)].join(' · ')
}

function TimingSummary({ visit }) {
  const timing = visitTiming(visit)
  if (timing.actual === null) {
    return (
      <span className="text-xs text-muted">
        Czas wizyty: brak pomiaru{timing.planned !== null ? ` · plan ${timing.planned} min` : ''}
      </span>
    )
  }
  const difference = timing.delta === null || timing.delta === 0
    ? 'zgodnie z planem'
    : timing.delta > 0
      ? `${Math.abs(timing.delta)} min dłużej`
      : `${Math.abs(timing.delta)} min krócej`
  return (
    <span className="text-xs text-muted">
      Czas wizyty: <b className="font-semibold text-ink">{timing.actual} min</b>
      {timing.planned !== null ? ` · plan ${timing.planned} min · ${difference}` : ''}
    </span>
  )
}

function VisitHistory({ data }) {
  const rows = data.historia || []
  if (!rows.length) return null
  return (
    <section className="border-t border-line pt-5" aria-labelledby="guest-history-title">
      <div className="flex items-baseline justify-between gap-3">
        <h4 id="guest-history-title" className="text-sm font-semibold text-ink">Historia wizyt</h4>
        <span className="text-xs text-muted">{data.historia_total ?? rows.length} wpisów</span>
      </div>
      <div className="mt-3 divide-y divide-line/70">
        {rows.map((visit, index) => (
          <div key={visit.reservation_id || `${visit.data}-${visit.godz_od}-${index}`} className="min-h-16 py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              <span className="font-semibold text-ink">
                {visit.data}{visit.godz_od ? ` · ${visit.godz_od}` : ''}{visit.liczba_osob ? ` · ${visit.liczba_osob} os.` : ''}
              </span>
              <span className="text-xs font-semibold text-muted">{STATUS_LABELS[visit.status] || visit.status}</span>
            </div>
            <div className="mt-1.5 flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3">
              <TimingSummary visit={visit} />
              {visitAllocation(visit) ? <span className="text-xs text-muted">{visitAllocation(visit)}</span> : null}
            </div>
          </div>
        ))}
      </div>
      {(data.historia_total || 0) > rows.length ? (
        <p className="mt-3 text-xs text-muted">Pokazano {rows.length} najnowszych wizyt.</p>
      ) : null}
    </section>
  )
}

export default function GuestProfileDialog({
  reservationId,
  onClose,
  onSaved,
  onDirtyChange,
  initialFocusRef,
  restoreFocusRef,
  closeLabel = 'Zamknij kartę gościa',
}) {
  const { isAdmin, can = () => false } = useAuth()
  const { confirm } = useToast()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [consentSaving, setConsentSaving] = useState(false)
  const [consentError, setConsentError] = useState(null)
  const [consentStatus, setConsentStatus] = useState('')
  const [retryVersion, setRetryVersion] = useState(0)
  const requestVersion = useRef(0)
  const readController = useRef(null)
  const writeController = useRef(null)
  const consentController = useRef(null)
  const consentKeysRef = useRef(new Map())
  const baseline = useRef('')
  const preserveSafeSnapshotOnNextRead = useRef(false)
  const canViewSensitiveNow = Boolean(isAdmin || can('rezerwacje.dane_wrazliwe'))
  const canViewNotesNow = Boolean(isAdmin || can('rezerwacje.notatki_wewnetrzne'))
  const visibilityKey = `${canViewSensitiveNow}:${canViewNotesNow}`
  const previousVisibilityKey = useRef(visibilityKey)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const version = ++requestVersion.current
    const controller = new AbortController()
    const preserveSafeSnapshot = preserveSafeSnapshotOnNextRead.current
    preserveSafeSnapshotOnNextRead.current = false
    readController.current?.abort()
    writeController.current?.abort()
    consentController.current?.abort()
    readController.current = controller
    writeController.current = null
    setLoading(!preserveSafeSnapshot)
    setLoadError(null)
    setSaveError(null)
    setSaved(false)
    setSaving(false)
    setConsentSaving(false)
    setConsentError(null)
    setConsentStatus('')
    consentKeysRef.current.clear()
    if (!preserveSafeSnapshot) {
      setData(null)
      setForm(null)
      baseline.current = ''
    }

    api(`/crm/rezerwacje/${encodeURIComponent(String(reservationId))}/profil`, 'GET', null, { signal: controller.signal })
      .then((response) => {
        if (version !== requestVersion.current) return
        const nextForm = formFromProfile(response)
        setData(response)
        setForm(nextForm)
        baseline.current = formSnapshot(nextForm)
      })
      .catch((error) => {
        if (version !== requestVersion.current || error?.name === 'AbortError') return
        setLoadError(error.message || 'Nie udało się otworzyć karty gościa.')
      })
      .finally(() => {
        if (version === requestVersion.current) setLoading(false)
      })

    return () => {
      controller.abort()
      if (readController.current === controller) readController.current = null
    }
  }, [reservationId, retryVersion])

  useEffect(() => () => {
    requestVersion.current += 1
    readController.current?.abort()
    writeController.current?.abort()
    consentController.current?.abort()
  }, [])

  useEffect(() => {
    if (previousVisibilityKey.current === visibilityKey) return
    previousVisibilityKey.current = visibilityKey
    // Bieżący render korzysta już z ``visibleData`` i natychmiast redaguje stare
    // PII. Ponowny odczyt synchronizuje kartę z aktualnym snapshotem backendu.
    preserveSafeSnapshotOnNextRead.current = true
    setRetryVersion((value) => value + 1)
  }, [visibilityKey])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    requestVersion.current += 1
    readController.current?.abort()
    writeController.current?.abort()
    consentController.current?.abort()
    consentController.current = null
    baseline.current = ''
    setData(null)
    setForm(null)
    setLoadError(null)
    setSaveError(null)
    setSaved(false)
    setLoading(false)
    setSaving(false)
    setConsentSaving(false)
    setConsentError(null)
    setConsentStatus('')
    consentKeysRef.current.clear()
    onCloseRef.current?.()
  }), [])

  const canEdit = Boolean(isAdmin && data?.capabilities?.can_edit)
  const canManageConsent = Boolean(isAdmin || can('rezerwacje.crm_zarzadzaj'))
  const dirty = Boolean(canEdit && form && formSnapshot(form) !== baseline.current)
  const returnLabel = closeLabel.startsWith('Wróć') ? closeLabel : (canEdit ? 'Zamknij' : 'Wróć')
  const visibleData = useMemo(() => {
    if (!data) return data
    const canViewSensitive = Boolean(
      canViewSensitiveNow && data.capabilities?.can_view_sensitive,
    )
    const canViewNotes = Boolean(
      canViewNotesNow && data.capabilities?.can_view_internal_notes,
    )
    const hidden = new Set(data.ukryte_pola || [])
    const profile = data.profil ? { ...data.profil } : null
    if (!canViewSensitive) {
      if (profile) {
        profile.tagi = []
        profile.alergie = null
        profile.dieta = null
      }
      hidden.add('profil.tagi')
      hidden.add('profil.alergie')
      hidden.add('profil.dieta')
    }
    if (!canViewNotes) {
      if (profile) profile.notatka = null
      hidden.add('profil.notatka')
    }
    return {
      ...data,
      profil: profile,
      ukryte_pola: [...hidden],
      capabilities: {
        ...(data.capabilities || {}),
        can_view_sensitive: canViewSensitive,
        can_view_internal_notes: canViewNotes,
      },
    }
  }, [canViewNotesNow, canViewSensitiveNow, data])

  useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
  }, [dirty, onDirtyChange])

  useEffect(() => {
    if (!dirty) return undefined
    const warnBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [dirty])

  const requestClose = useCallback(async () => {
    if (saving || consentSaving) return
    if (dirty) {
      const discard = await confirm(
        'Odrzucić niezapisane zmiany w profilu gościa?',
        {
          title: 'Niezapisane zmiany',
          confirmText: 'Odrzuć zmiany',
          cancelText: 'Wróć do profilu',
        },
      )
      if (!discard) return
    }
    onClose?.({ dirtyConfirmed: dirty })
  }, [confirm, consentSaving, dirty, onClose, saving])

  const save = useCallback(async (event) => {
    event?.preventDefault()
    if (!canEdit || !form || saving) return
    const controller = new AbortController()
    writeController.current?.abort()
    writeController.current = controller
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const response = await api(
        `/crm/rezerwacje/${encodeURIComponent(String(reservationId))}/profil`,
        'PUT',
        formPayload(form),
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      const nextForm = formFromProfile(response)
      setData(response)
      setForm(nextForm)
      baseline.current = formSnapshot(nextForm)
      setSaved(true)
      onSaved?.(response)
    } catch (error) {
      if (error?.name !== 'AbortError') setSaveError(error.message || 'Nie udało się zapisać profilu gościa.')
    } finally {
      if (writeController.current === controller) {
        writeController.current = null
        setSaving(false)
      }
    }
  }, [canEdit, form, onSaved, reservationId, saving])

  const recordConsent = useCallback(async (decision, source) => {
    if (!canManageConsent || consentSaving || dirty) return
    const documentVersion = data?.zgody?.current_document_version
    if (!documentVersion) {
      setConsentError('Brak aktualnej wersji treści zgody. Odśwież kartę gościa.')
      return
    }
    const fingerprint = JSON.stringify([
      String(reservationId),
      decision,
      source,
      documentVersion,
    ])
    let idempotencyKey = consentKeysRef.current.get(fingerprint)
    if (!idempotencyKey) {
      idempotencyKey = nowyKluczIdempotencji('crm-consent')
      consentKeysRef.current.set(fingerprint, idempotencyKey)
    }
    const controller = new AbortController()
    consentController.current?.abort()
    consentController.current = controller
    setConsentSaving(true)
    setConsentError(null)
    setConsentStatus('')
    try {
      const response = await api(
        `/crm/rezerwacje/${encodeURIComponent(String(reservationId))}/zgody`,
        'POST',
        {
          decision,
          source,
          document_version: documentVersion,
        },
        {
          signal: controller.signal,
          headers: {
            'Idempotency-Key': idempotencyKey,
          },
        },
      )
      if (controller.signal.aborted) return
      consentKeysRef.current.delete(fingerprint)
      setData((current) => current ? { ...current, zgody: response } : current)
      setConsentStatus(
        decision === 'grant'
          ? 'Zapisano dowód udzielenia zgody.'
          : decision === 'decline'
            ? 'Zapisano odmowę udzielenia zgody.'
            : 'Zapisano wycofanie zgody.',
      )
      onSaved?.({ consent: response })
    } catch (error) {
      if (error?.name !== 'AbortError') {
        setConsentError(error.message || 'Nie udało się zapisać zdarzenia zgody.')
      }
    } finally {
      if (consentController.current === controller) {
        consentController.current = null
        setConsentSaving(false)
      }
    }
  }, [canManageConsent, consentSaving, data?.zgody?.current_document_version, dirty, onSaved, reservationId])

  const title = useMemo(() => data?.nazwisko ? `Karta gościa · ${data.nazwisko}` : 'Karta gościa', [data?.nazwisko])

  return (
    <DialogFrame
      title={title}
      closeLabel={closeLabel}
      onClose={requestClose}
      maxWidth="max-w-2xl"
      initialFocusRef={initialFocusRef}
      restoreFocusRef={restoreFocusRef}
    >
      {loading ? <ProfileSkeleton /> : loadError ? (
        <div role="alert" className="space-y-4">
          <Banner variant="danger">{loadError}</Banner>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="subtle" onClick={requestClose}>Wróć</Button>
            <Button onClick={() => setRetryVersion((value) => value + 1)}>
              <Icon name="refresh" className="h-4 w-4" /> Ponów
            </Button>
          </div>
        </div>
      ) : visibleData && form ? (
        <form onSubmit={save} className="space-y-5">
          <GuestSummary data={visibleData} />

          {visibleData.identity?.confident === false ? (
            <Banner variant="info">Brak jednoznacznego telefonu lub e-maila. Historia obejmuje wyłącznie tę rezerwację.</Banner>
          ) : null}

          {canEdit ? <ProfileForm form={form} setForm={setForm} saving={saving} /> : <ReadOnlyProfile data={visibleData} />}
          <ConsentHistory
            consent={visibleData.zgody}
            canManage={canManageConsent}
            disabled={dirty || saving}
            saving={consentSaving}
            error={consentError}
            status={consentStatus}
            onRecord={recordConsent}
          />
          <VisitHistory data={visibleData} />

          {saveError ? <div role="alert"><Banner variant="danger">{saveError}</Banner></div> : null}
          <p className="min-h-5 text-xs text-success" role="status" aria-live="polite">{saved ? 'Zapisano profil gościa.' : ''}</p>

          <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
            <Button variant="subtle" onClick={requestClose}>{returnLabel}</Button>
            {canEdit ? (
              <Button type="submit" loading={saving} loadingLabel="Zapisuję profil">
                <Icon name="check" className="h-4 w-4" /> Zapisz profil
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
    </DialogFrame>
  )
}
