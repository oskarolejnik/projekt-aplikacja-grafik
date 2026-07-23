import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, pobierzPlikPost } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { DialogFrame } from '../ui/DialogFrame'

const SUMMARY_FIELDS = [
  {
    key: 'duplicates',
    label: 'Możliwe duplikaty',
    aliases: ['mozliwe_duplikaty', 'possible_duplicates', 'duplikaty'],
  },
  {
    key: 'missingContact',
    label: 'Bez kontaktu',
    aliases: ['bez_kontaktu', 'missing_contact', 'brak_kontaktu'],
  },
  {
    key: 'consentIssues',
    label: 'Zgody bez dowodu',
    aliases: ['zgody_bez_dowodu', 'consent_issues', 'problemy_zgody'],
  },
  {
    key: 'orphanProfiles',
    label: 'Profile bez historii',
    aliases: ['profile_osierocone', 'orphan_profiles', 'profile_bez_historii'],
  },
]

const valueFrom = (source, aliases, fallback = 0) => {
  for (const alias of aliases) {
    if (source?.[alias] !== undefined && source?.[alias] !== null) {
      const value = Number(source[alias])
      return Number.isFinite(value) && value >= 0 ? value : fallback
    }
  }
  return fallback
}

const arrayFrom = (source, aliases) => {
  for (const alias of aliases) {
    if (Array.isArray(source?.[alias])) return source[alias]
  }
  return []
}

const personFrom = (source) => {
  const value = source || {}
  return {
    name: value.nazwisko || value.name || value.label || 'Gość bez nazwy',
    contact: value.telefon || value.phone || value.email || value.masked_contact || null,
    visits: value.wizyt ?? value.visits ?? value.historia_total ?? null,
  }
}

const candidateSides = (candidate) => ({
  source: personFrom(
    candidate?.source
      || candidate?.zrodlo
      || candidate?.source_guest
      || candidate?.left,
  ),
  target: personFrom(
    candidate?.target
      || candidate?.cel
      || candidate?.target_guest
      || candidate?.right,
  ),
})

const candidateRefs = (candidate) => ({
  source_ref: candidate?.source_ref
    ?? candidate?.source_profile_ref
    ?? candidate?.zrodlo_ref
    ?? candidate?.source?.profil_ref
    ?? candidate?.zrodlo?.profil_ref,
  target_ref: candidate?.target_ref
    ?? candidate?.target_profile_ref
    ?? candidate?.cel_ref
    ?? candidate?.target?.profil_ref
    ?? candidate?.cel?.profil_ref,
})

const normalizeQuality = (response) => {
  const summary = response?.podsumowanie || response?.summary || {}
  const candidates = arrayFrom(response, [
    'kandydaci',
    'candidates',
    'mozliwe_duplikaty',
    'possible_duplicates',
  ])
  const activeMerges = arrayFrom(response, [
    'aktywne_scalenia',
    'active_merges',
    'merges',
  ])
  return {
    summary: SUMMARY_FIELDS.map((field) => ({
      ...field,
      value: valueFrom(
        summary,
        field.aliases,
        field.key === 'duplicates' ? candidates.length : 0,
      ),
    })),
    candidates,
    activeMerges,
  }
}

const previewConflicts = (preview) => arrayFrom(preview, ['konflikty', 'conflicts'])
const previewWarnings = (preview) => arrayFrom(preview, ['ostrzezenia', 'warnings'])

const conflictLabel = (conflict) => (
  conflict?.etykieta || conflict?.label || conflict?.pole || conflict?.field || 'Różne dane'
)

const conflictValues = (conflict) => ({
  source: conflict?.source ?? conflict?.zrodlo ?? conflict?.left ?? 'Brak danych',
  target: conflict?.target ?? conflict?.cel ?? conflict?.right ?? 'Brak danych',
})

const mergeId = (merge) => merge?.id ?? merge?.merge_id ?? merge?.scalenie_id

const mergeSides = (merge) => ({
  source: personFrom(merge?.source || merge?.zrodlo || merge?.source_guest),
  target: personFrom(merge?.target || merge?.cel || merge?.target_guest),
})

const operationKey = (prefix) => {
  const random = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${random}`.slice(0, 128)
}

const errorMessage = (error, fallback) => (
  error?.message || fallback
)

export default function CrmGovernanceTools({
  searchBody = {},
  onChanged,
  canManage = true,
  canExport = true,
  exportReady = true,
}) {
  const [open, setOpen] = useState(false)
  const [quality, setQuality] = useState(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [previewState, setPreviewState] = useState(null)
  const [undoState, setUndoState] = useState(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [status, setStatus] = useState('')
  const searchBodyKey = useMemo(() => JSON.stringify(searchBody), [searchBody])
  const controllersRef = useRef(new Set())
  const generationRef = useRef(0)
  const qualityControllerRef = useRef(null)
  const previewControllerRef = useRef(null)
  const initialLoadStartedRef = useRef(false)
  const previewTriggerRef = useRef(null)
  const undoTriggerRef = useRef(null)
  const mergeKeyRef = useRef(null)
  const undoKeysRef = useRef(new Map())

  const registerController = useCallback(() => {
    const controller = new AbortController()
    controllersRef.current.add(controller)
    return controller
  }, [])

  const releaseController = useCallback((controller) => {
    controllersRef.current.delete(controller)
  }, [])

  const abortAll = useCallback(() => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
    qualityControllerRef.current = null
    previewControllerRef.current = null
  }, [])

  const loadQuality = useCallback(async () => {
    if (!canManage) return
    qualityControllerRef.current?.abort()
    const controller = registerController()
    const generation = generationRef.current
    const background = quality !== null
    qualityControllerRef.current = controller
    if (background) setRefreshing(true)
    else setLoading(true)
    setLoadError('')
    try {
      const response = await api('/crm/jakosc', 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted || generation !== generationRef.current) return
      setQuality(normalizeQuality(response))
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current || error?.name === 'AbortError') return
      setLoadError(errorMessage(error, 'Nie udało się sprawdzić jakości danych CRM.'))
    } finally {
      releaseController(controller)
      if (qualityControllerRef.current === controller) qualityControllerRef.current = null
      if (generation === generationRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [canManage, quality, registerController, releaseController])

  useEffect(() => {
    if (
      canManage
      && open
      && quality === null
      && !loading
      && !qualityControllerRef.current
      && !initialLoadStartedRef.current
    ) {
      initialLoadStartedRef.current = true
      void loadQuality()
    }
  }, [canManage, loadQuality, loading, open, quality])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    generationRef.current += 1
    abortAll()
    setOpen(false)
    setQuality(null)
    setLoading(false)
    setRefreshing(false)
    setLoadError('')
    setPreviewState(null)
    setUndoState(null)
    setExporting(false)
    setExportError('')
    setStatus('')
    mergeKeyRef.current = null
    undoKeysRef.current.clear()
    initialLoadStartedRef.current = false
    previewTriggerRef.current = null
    undoTriggerRef.current = null
  }), [abortAll])

  useEffect(() => () => {
    generationRef.current += 1
    abortAll()
  }, [abortAll])

  const openPreview = useCallback(async (candidate, trigger) => {
    const refs = candidateRefs(candidate)
    if (refs.source_ref == null || refs.target_ref == null) {
      setStatus('')
      setLoadError('Nie można otworzyć porównania. Odśwież narzędzia jakości.')
      return
    }
    previewControllerRef.current?.abort()
    previewTriggerRef.current = trigger
    mergeKeyRef.current = operationKey('crm-merge')
    setStatus('')
    setPreviewState({
      candidate,
      refs,
      preview: null,
      loading: true,
      saving: false,
      error: '',
      confirmed: false,
    })
    const controller = registerController()
    previewControllerRef.current = controller
    const generation = generationRef.current
    const matchesRequest = (current) => (
      current?.refs?.source_ref === refs.source_ref
      && current?.refs?.target_ref === refs.target_ref
    )
    try {
      const response = await api(
        '/crm/scalenia/podglad',
        'POST',
        refs,
        { signal: controller.signal },
      )
      if (controller.signal.aborted || generation !== generationRef.current) return
      setPreviewState((current) => matchesRequest(current) ? {
        ...current,
        preview: response,
        loading: false,
      } : current)
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current || error?.name === 'AbortError') return
      setPreviewState((current) => matchesRequest(current) ? {
        ...current,
        loading: false,
        error: errorMessage(error, 'Nie udało się porównać profili.'),
      } : current)
    } finally {
      releaseController(controller)
      if (previewControllerRef.current === controller) previewControllerRef.current = null
    }
  }, [registerController, releaseController])

  const retryPreview = useCallback(() => {
    if (!previewState?.candidate) return
    void openPreview(previewState.candidate, previewTriggerRef.current)
  }, [openPreview, previewState?.candidate])

  const mergeCandidate = useCallback(async () => {
    if (!previewState?.preview || !previewState.confirmed || previewState.saving) return
    const controller = registerController()
    const generation = generationRef.current
    const expectedVersion = previewState.preview?.expected_version
      ?? previewState.preview?.wersja
      ?? previewState.preview?.version
    const body = {
      ...previewState.refs,
      reason_code: 'duplicate_confirmed',
      ...(expectedVersion == null ? {} : { expected_version: expectedVersion }),
    }
    setPreviewState((current) => current ? { ...current, saving: true, error: '' } : current)
    try {
      await api('/crm/scalenia', 'POST', body, {
        signal: controller.signal,
        headers: { 'Idempotency-Key': mergeKeyRef.current || operationKey('crm-merge') },
      })
      if (controller.signal.aborted || generation !== generationRef.current) return
      setPreviewState(null)
      mergeKeyRef.current = null
      setStatus('Profile zostały scalone. Możesz cofnąć tę zmianę poniżej.')
      await loadQuality()
      if (generation === generationRef.current) onChanged?.()
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current || error?.name === 'AbortError') return
      setPreviewState((current) => current ? {
        ...current,
        saving: false,
        error: errorMessage(error, 'Nie udało się scalić profili. Spróbuj ponownie.'),
      } : current)
    } finally {
      releaseController(controller)
    }
  }, [loadQuality, onChanged, previewState, registerController, releaseController])

  const requestUndo = useCallback((merge, trigger) => {
    const id = mergeId(merge)
    if (id == null) {
      setLoadError('Nie można cofnąć tej zmiany. Odśwież narzędzia jakości.')
      return
    }
    undoTriggerRef.current = trigger
    if (!undoKeysRef.current.has(id)) {
      undoKeysRef.current.set(id, operationKey('crm-merge-undo'))
    }
    setStatus('')
    setUndoState({ merge, id, saving: false, error: '' })
  }, [])

  const undoMerge = useCallback(async () => {
    if (!undoState || undoState.saving) return
    const controller = registerController()
    const generation = generationRef.current
    setUndoState((current) => current ? { ...current, saving: true, error: '' } : current)
    try {
      await api(`/crm/scalenia/${encodeURIComponent(String(undoState.id))}/cofnij`, 'POST', {}, {
        signal: controller.signal,
        headers: {
          'Idempotency-Key': undoKeysRef.current.get(undoState.id)
            || operationKey('crm-merge-undo'),
        },
      })
      if (controller.signal.aborted || generation !== generationRef.current) return
      undoKeysRef.current.delete(undoState.id)
      setUndoState(null)
      setStatus('Scalenie zostało cofnięte. Oba profile znów są rozdzielone.')
      await loadQuality()
      if (generation === generationRef.current) onChanged?.()
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current || error?.name === 'AbortError') return
      setUndoState((current) => current ? {
        ...current,
        saving: false,
        error: errorMessage(error, 'Nie udało się cofnąć scalenia. Spróbuj ponownie.'),
      } : current)
    } finally {
      releaseController(controller)
    }
  }, [loadQuality, onChanged, registerController, releaseController, undoState])

  const exportCurrent = useCallback(async () => {
    if (!canExport || !exportReady || exporting) return
    const controller = registerController()
    const generation = generationRef.current
    setExporting(true)
    setExportError('')
    setStatus('')
    const today = new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'Europe/Warsaw',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date())
    try {
      await pobierzPlikPost(
        '/crm/eksport',
        searchBody || {},
        `goscie_crm_${today}.csv`,
        { signal: controller.signal },
      )
      if (controller.signal.aborted || generation !== generationRef.current) return
      setStatus('Eksport bieżącego wyniku został pobrany.')
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current || error?.name === 'AbortError') return
      setExportError(errorMessage(error, 'Nie udało się przygotować eksportu.'))
    } finally {
      releaseController(controller)
      if (generation === generationRef.current) setExporting(false)
    }
  }, [canExport, exportReady, exporting, registerController, releaseController, searchBody])

  useEffect(() => {
    setExportError('')
    setStatus('')
  }, [searchBodyKey])

  const summary = quality?.summary || []
  const candidates = quality?.candidates || []
  const activeMerges = quality?.activeMerges || []
  const panelStateLabel = useMemo(() => {
    if (!open) return 'Pokaż narzędzia'
    if (refreshing) return 'Aktualizuję'
    return 'Ukryj narzędzia'
  }, [open, refreshing])

  return (
    <section className="border-t border-line pt-5" aria-labelledby="crm-governance-title">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 id="crm-governance-title" className="font-display text-base font-semibold text-ink">
            {canManage ? 'Jakość danych i eksport' : 'Eksport danych gości'}
          </h3>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
            {canManage
              ? 'Sprawdź możliwe duplikaty i pobierz dokładnie bieżący wynik. Żadna sugestia nie scala profili automatycznie.'
              : 'Pobierz dokładnie bieżący wynik z aktywnymi filtrami. Pobranie zostanie zapisane w audycie.'}
          </p>
        </div>
        <Button
          variant="subtle"
          className="w-full shrink-0 sm:w-auto"
          aria-expanded={open}
          aria-controls="crm-governance-panel"
          onClick={() => setOpen((current) => !current)}
        >
          {panelStateLabel}
          <Icon
            name="chevronDown"
            className={`h-4 w-4 transition motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          />
        </Button>
      </div>

      {open ? (
        <div id="crm-governance-panel" className="mt-5 space-y-6">
          {canManage ? <>
            {loadError ? (
              <div role="alert">
                <Banner variant="danger">
                  <div className="flex flex-wrap items-center gap-3">
                    <span>{loadError}</span>
                    <Button variant="ghost" size="sm" onClick={() => void loadQuality()}>
                      <Icon name="refresh" className="h-4 w-4" /> Ponów
                    </Button>
                  </div>
                </Banner>
              </div>
            ) : null}

            {loading && !quality ? <QualitySkeleton /> : quality ? (
            <>
              <div className="overflow-hidden rounded-xl border border-line bg-white/[0.025]">
                <dl className="grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-4 sm:divide-y-0">
                  {summary.map((item) => (
                    <div key={item.key} className="min-w-0 px-4 py-3">
                      <dt className="text-xs font-semibold text-muted">{item.label}</dt>
                      <dd className="mt-1 font-display text-xl font-semibold tabular-nums text-ink">{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              <section aria-labelledby="crm-duplicates-title">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h4 id="crm-duplicates-title" className="text-sm font-semibold text-ink">Do sprawdzenia</h4>
                    <p className="mt-1 text-xs leading-relaxed text-muted">Porównaj dane przed podjęciem decyzji.</p>
                  </div>
                  {refreshing ? (
                    <span className="text-xs text-muted" role="status" aria-live="polite">Aktualizuję dane…</span>
                  ) : (
                    <Button variant="subtle" size="sm" onClick={() => void loadQuality()}>
                      <Icon name="refresh" className="h-4 w-4" /> Odśwież
                    </Button>
                  )}
                </div>
                {candidates.length ? (
                  <ul className="mt-3 divide-y divide-line rounded-xl border border-line" aria-label="Kandydaci na duplikaty">
                    {candidates.map((candidate, index) => (
                      <CandidateRow
                        key={candidate?.id ?? candidate?.candidate_id ?? index}
                        candidate={candidate}
                        onPreview={(event) => void openPreview(candidate, event.currentTarget)}
                      />
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">
                    Brak profili wymagających porównania.
                  </p>
                )}
              </section>

              <section aria-labelledby="crm-active-merges-title">
                <h4 id="crm-active-merges-title" className="text-sm font-semibold text-ink">Aktywne scalenia</h4>
                {activeMerges.length ? (
                  <ul className="mt-3 divide-y divide-line rounded-xl border border-line" aria-label="Aktywne scalenia profili">
                    {activeMerges.map((merge, index) => (
                      <MergeRow
                        key={mergeId(merge) ?? index}
                        merge={merge}
                        onUndo={(event) => requestUndo(merge, event.currentTarget)}
                      />
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-muted">Nie ma aktywnych scaleń do cofnięcia.</p>
                )}
              </section>
            </>
            ) : null}
          </> : null}

          {canExport ? <section className={canManage ? 'border-t border-line pt-5' : ''} aria-labelledby="crm-export-title">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h4 id="crm-export-title" className="text-sm font-semibold text-ink">Eksport bieżącego wyniku</h4>
                <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
                  Plik uwzględni filtry aktywne w bazie gości. Pobranie zostanie zapisane w audycie.
                </p>
              </div>
              <Button
                variant="ghost"
                className="w-full sm:w-auto"
                onClick={() => void exportCurrent()}
                loading={exporting}
                loadingLabel="Przygotowuję…"
                disabled={!exportReady}
              >
                <Icon name="download" className="h-4 w-4" /> Pobierz CSV
              </Button>
            </div>
            {exportError ? (
              <div className="mt-3" role="alert">
                <Banner variant="danger">
                  <div className="flex flex-wrap items-center gap-3">
                    <span>{exportError}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!exportReady}
                      onClick={() => void exportCurrent()}
                    >
                      Ponów eksport
                    </Button>
                  </div>
                </Banner>
              </div>
            ) : null}
          </section> : null}

          <p className="min-h-5 text-xs text-success" role="status" aria-live="polite">{status}</p>
        </div>
      ) : null}

      {previewState ? (
        <MergePreviewDialog
          state={previewState}
          restoreFocusRef={previewTriggerRef}
          onClose={() => {
            if (previewState.saving) return
            previewControllerRef.current?.abort()
            previewControllerRef.current = null
            setPreviewState(null)
            mergeKeyRef.current = null
          }}
          onRetry={retryPreview}
          onConfirmedChange={(confirmed) => setPreviewState((current) => (
            current ? { ...current, confirmed } : current
          ))}
          onMerge={() => void mergeCandidate()}
        />
      ) : null}

      {undoState ? (
        <UndoDialog
          state={undoState}
          restoreFocusRef={undoTriggerRef}
          onClose={() => {
            if (!undoState.saving) setUndoState(null)
          }}
          onUndo={() => void undoMerge()}
        />
      ) : null}
    </section>
  )
}

function QualitySkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Sprawdzanie jakości danych">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <span key={item} className="h-20 animate-pulse bg-white/[0.04] motion-reduce:animate-none" />
        ))}
      </div>
      <span className="block h-16 animate-pulse rounded-xl bg-white/[0.04] motion-reduce:animate-none" />
      <span className="sr-only">Sprawdzanie jakości danych…</span>
    </div>
  )
}

function PersonSummary({ person }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-semibold text-ink">{person.name}</p>
      <p className="mt-0.5 truncate text-xs text-muted">{person.contact || 'Brak kontaktu do wyświetlenia'}</p>
      {person.visits != null ? <p className="mt-0.5 text-xs text-muted">{person.visits} wizyt</p> : null}
    </div>
  )
}

function CandidateRow({ candidate, onPreview }) {
  const { source, target } = candidateSides(candidate)
  const reason = candidate?.powod || candidate?.reason_label || candidate?.reason || 'Podobne dane kontaktowe'
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <PersonSummary person={source} />
        <span className="hidden text-muted sm:inline" aria-hidden="true">↔</span>
        <PersonSummary person={target} />
      </div>
      <div className="flex flex-col gap-2 sm:items-end">
        <p className="text-xs text-muted">{reason}</p>
        <Button variant="ghost" size="sm" className="w-full sm:w-auto" onClick={onPreview}>
          Porównaj
        </Button>
      </div>
    </li>
  )
}

function MergeRow({ merge, onUndo }) {
  const { source, target } = mergeSides(merge)
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ink">
          <span className="font-semibold">{source.name}</span>
          <span className="px-2 text-muted" aria-hidden="true">→</span>
          <span className="font-semibold">{target.name}</span>
        </p>
        <p className="mt-1 text-xs text-muted">Historia jest połączona, ale zmiana pozostaje odwracalna.</p>
      </div>
      <Button variant="subtle" size="sm" className="w-full sm:w-auto" onClick={onUndo}>
        Cofnij
      </Button>
    </li>
  )
}

function MergePreviewDialog({
  state,
  restoreFocusRef,
  onClose,
  onRetry,
  onConfirmedChange,
  onMerge,
}) {
  const cancelRef = useRef(null)
  const candidate = candidateSides(state.candidate)
  const previewSource = personFrom(state.preview?.source || state.preview?.zrodlo)
  const previewTarget = personFrom(state.preview?.target || state.preview?.cel)
  const source = state.preview?.source || state.preview?.zrodlo ? previewSource : candidate.source
  const target = state.preview?.target || state.preview?.cel ? previewTarget : candidate.target
  const conflicts = previewConflicts(state.preview)
  const warnings = previewWarnings(state.preview)

  return (
    <DialogFrame
      title="Porównaj profile"
      closeLabel="Zamknij porównanie"
      onClose={onClose}
      maxWidth="max-w-2xl"
      initialFocusRef={cancelRef}
      restoreFocusRef={restoreFocusRef}
    >
      {state.loading ? <QualitySkeleton /> : state.error && !state.preview ? (
        <div className="space-y-4" role="alert">
          <Banner variant="danger">{state.error}</Banner>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button
              ref={cancelRef}
              type="button"
              onClick={onClose}
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl bg-white/[0.04] px-5 py-2.5 text-sm font-semibold text-muted transition hover:bg-white/[0.08] hover:text-ink active:scale-[0.98]"
            >
              Anuluj
            </button>
            <Button onClick={onRetry}><Icon name="refresh" className="h-4 w-4" /> Ponów</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-line bg-white/[0.025] p-4">
              <p className="text-xs font-semibold text-muted">Profil źródłowy</p>
              <div className="mt-2"><PersonSummary person={source} /></div>
            </div>
            <div className="rounded-xl border border-line bg-white/[0.025] p-4">
              <p className="text-xs font-semibold text-muted">Profil docelowy</p>
              <div className="mt-2"><PersonSummary person={target} /></div>
            </div>
          </div>

          {conflicts.length ? (
            <section aria-labelledby="crm-merge-conflicts">
              <h4 id="crm-merge-conflicts" className="text-sm font-semibold text-ink">Różnice wymagające uwagi</h4>
              <dl className="mt-2 divide-y divide-line rounded-xl border border-line">
                {conflicts.map((conflict, index) => {
                  const values = conflictValues(conflict)
                  return (
                    <div key={`${conflictLabel(conflict)}-${index}`} className="grid gap-2 p-3 text-sm sm:grid-cols-[9rem_1fr_1fr]">
                      <dt className="font-semibold text-muted">{conflictLabel(conflict)}</dt>
                      <dd className="break-words text-ink">{String(values.source)}</dd>
                      <dd className="break-words text-ink">{String(values.target)}</dd>
                    </div>
                  )
                })}
              </dl>
            </section>
          ) : (
            <p className="text-sm text-muted">Nie znaleziono sprzecznych pól profilu.</p>
          )}

          {warnings.map((warning, index) => (
            <Banner key={index} variant="warn">{typeof warning === 'string' ? warning : warning?.message}</Banner>
          ))}
          <Banner variant="warn">
            Scal wyłącznie profile tej samej osoby. Zgody marketingowe nie są przenoszone ani wznawiane przez scalenie.
          </Banner>

          <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-line px-3 py-3 text-sm text-ink">
            <input
              type="checkbox"
              checked={state.confirmed}
              onChange={(event) => onConfirmedChange(event.target.checked)}
              disabled={state.saving}
              className="mt-0.5 h-5 w-5 shrink-0 accent-mint"
            />
            <span>Potwierdzam, że oba profile dotyczą tej samej osoby i sprawdziłem/am różnice.</span>
          </label>

          {state.error ? <div role="alert"><Banner variant="danger">{state.error}</Banner></div> : null}
          <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
            <button
              ref={cancelRef}
              type="button"
              onClick={onClose}
              disabled={state.saving}
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl bg-white/[0.04] px-5 py-2.5 text-sm font-semibold text-muted transition hover:bg-white/[0.08] hover:text-ink active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
            >
              Anuluj
            </button>
            <Button
              variant="danger"
              onClick={onMerge}
              disabled={!state.confirmed}
              loading={state.saving}
              loadingLabel="Scalam…"
            >
              Scal profile
            </Button>
          </div>
        </div>
      )}
    </DialogFrame>
  )
}

function UndoDialog({ state, restoreFocusRef, onClose, onUndo }) {
  const cancelRef = useRef(null)
  const { source, target } = mergeSides(state.merge)
  return (
    <DialogFrame
      title="Cofnąć scalenie?"
      closeLabel="Zamknij potwierdzenie"
      onClose={onClose}
      maxWidth="max-w-md"
      initialFocusRef={cancelRef}
      restoreFocusRef={restoreFocusRef}
    >
      <div className="space-y-5">
        <Banner variant="warn">
          Profile „{source.name}” i „{target.name}” znów będą miały oddzielne historie. Żadne dane nie zostaną usunięte.
        </Banner>
        {state.error ? <div role="alert"><Banner variant="danger">{state.error}</Banner></div> : null}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={onClose}
            disabled={state.saving}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl bg-white/[0.04] px-5 py-2.5 text-sm font-semibold text-muted transition hover:bg-white/[0.08] hover:text-ink active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
          >
            Zostaw scalenie
          </button>
          <Button
            variant="danger"
            onClick={onUndo}
            loading={state.saving}
            loadingLabel="Cofam…"
          >
            Cofnij scalenie
          </Button>
        </div>
      </div>
    </DialogFrame>
  )
}
