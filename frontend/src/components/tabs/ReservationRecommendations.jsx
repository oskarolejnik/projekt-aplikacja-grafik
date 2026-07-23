import { useEffect, useMemo, useRef, useState } from 'react'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { useToast } from '../ui/Toast'

const ACCEPT_REASON = 'confirmed_after_simulation'
const DEFAULT_REJECT_REASON = 'keep_current_policy'

const REJECT_REASONS = [
  { value: DEFAULT_REJECT_REASON, label: 'Pozostawiam obecną zasadę' },
  { value: 'seasonal_sample', label: 'Próba jest sezonowa lub nietypowa' },
  { value: 'operational_decision', label: 'Zmiana nie pasuje do pracy lokalu' },
]

const finiteNumber = (value) => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const firstNumber = (...values) => {
  for (const value of values) {
    const parsed = finiteNumber(value)
    if (parsed !== null) return parsed
  }
  return null
}

const readThreshold = (thresholds, keys, fallback) => {
  for (const key of keys) {
    const value = finiteNumber(thresholds?.[key])
    if (value !== null) return value
  }
  return fallback
}

const segmentLabel = (segment) => {
  const normalized = String(segment || '').trim().toLowerCase()
  if (['1-2', '1_2', '1–2'].includes(normalized)) return '1–2 os.'
  if (['3-4', '3_4', '3–4'].includes(normalized)) return '3–4 os.'
  if (['5+', '5_plus', '5-plus'].includes(normalized)) return '5+ os.'
  return normalized ? `${segment} os.` : 'Nieznana grupa'
}

const formatMinutes = (value) => {
  const minutes = finiteNumber(value)
  if (minutes === null) return '—'
  const rounded = Math.round(minutes)
  if (rounded < 60) return `${rounded} min`
  const hours = Math.floor(rounded / 60)
  const rest = rounded % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

const formatSigned = (value) => {
  const number = finiteNumber(value)
  if (number === null) return '—'
  if (number === 0) return 'bez zmiany'
  return `${number > 0 ? '+' : '−'}${Math.abs(Math.round(number))}`
}

const normalizeDecision = (value) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (['accepted', 'przyjeta', 'przyjęta', 'zaakceptowana'].includes(normalized)) return 'accepted'
  if (['rejected', 'odrzucona', 'odrzucone'].includes(normalized)) return 'rejected'
  return 'pending'
}

const decisionRecordFor = (decisions, hash) => {
  if (Array.isArray(decisions)) {
    return decisions.find((item) => (
      item?.hash === hash
      || item?.rekomendacja_hash === hash
      || item?.recommendation_hash === hash
    ))
  }
  return decisions && typeof decisions === 'object' ? decisions[hash] : null
}

const decisionFor = (candidate, decisions, localDecisions) => {
  if (localDecisions[candidate.hash]) return localDecisions[candidate.hash]
  const record = decisionRecordFor(decisions, candidate.hash)
  return normalizeDecision(
    record?.decyzja
    || record?.stan
    || record?.decision
    || candidate.stan,
  )
}

const simulationFacts = (simulation) => {
  const summary = simulation?.summary || {}
  const checked = firstNumber(
    summary.sprawdzone_sloty,
    summary.liczba_sprawdzonych_slotow,
    summary.checked_slots,
    summary.sprawdzone,
  )
  const before = firstNumber(
    summary.dostepne_przed,
    summary.dostepne_obecnie,
    summary.current_available_slots,
    summary.obecnie?.dostepne,
  )
  const after = firstNumber(
    summary.dostepne_po,
    summary.dostepne_po_zmianie,
    summary.proposed_available_slots,
    summary.po_zmianie?.dostepne,
  )
  const difference = firstNumber(
    summary.roznica,
    summary.zmiana_dostepnych_slotow,
    summary.delta_available_slots,
    before !== null && after !== null ? after - before : null,
  )
  return { checked, before, after, difference }
}

const rangeReady = (range) => Boolean(
  range?.start
  && range?.end
  && range.start <= range.end,
)

function EvidenceFact({ label, value, detail }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold text-muted">{label}</dt>
      <dd className="mt-1 text-base font-semibold tabular-nums text-ink">{value}</dd>
      {detail ? <dd className="mt-0.5 text-xs leading-relaxed text-muted">{detail}</dd> : null}
    </div>
  )
}

function SimulationSummary({ simulation }) {
  const facts = simulationFacts(simulation)
  const hasNumbers = Object.values(facts).some((value) => value !== null)
  const note = simulation?.summary?.opis
    || simulation?.summary?.uwaga
    || simulation?.summary?.note

  return (
    <div className="space-y-4" aria-live="polite">
      <div>
        <h4 className="text-sm font-semibold text-ink">Wpływ został policzony</h4>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
          Porównanie używa bieżących rezerwacji i tego samego silnika dostępności, który obsługuje zapisy.
        </p>
      </div>

      {hasNumbers ? (
        <dl className="grid grid-cols-2 gap-x-5 gap-y-4 border-y border-line py-4 sm:grid-cols-4">
          <EvidenceFact label="Sprawdzone sloty" value={facts.checked ?? '—'} />
          <EvidenceFact label="Dostępne obecnie" value={facts.before ?? '—'} />
          <EvidenceFact label="Po zmianie" value={facts.after ?? '—'} />
          <EvidenceFact
            label="Różnica"
            value={formatSigned(facts.difference)}
            detail="liczba dostępnych startów"
          />
        </dl>
      ) : (
        <p className="border-y border-line py-4 text-sm text-muted">
          Symulacja potwierdziła wpływ kandydackiej reguły. Szczegółowe liczby nie są dostępne w tym wyniku.
        </p>
      )}

      {note ? <p className="text-sm leading-relaxed text-muted">{note}</p> : null}
      <Banner variant="info">
        To snapshot dostępności, nie prognoza popytu. Decyzja nie zmieni czasu ani przydziału
        istniejących rezerwacji.
      </Banner>
    </div>
  )
}

export default function ReservationRecommendations({
  data,
  range,
  canDecide = false,
  onChanged,
}) {
  const { confirm } = useToast()
  const [simulations, setSimulations] = useState({})
  const [simulationErrors, setSimulationErrors] = useState({})
  const [decisionErrors, setDecisionErrors] = useState({})
  const [busyByHash, setBusyByHash] = useState({})
  const [rejectReasons, setRejectReasons] = useState({})
  const [localDecisions, setLocalDecisions] = useState({})
  const controllersRef = useRef(new Map())
  const decisionKeysRef = useRef(new Map())
  const contextKey = `${range?.start || ''}:${range?.end || ''}`

  const candidates = useMemo(
    () => (Array.isArray(data?.rekomendacje) ? data.rekomendacje : []),
    [data?.rekomendacje],
  )
  const thresholds = data?.progi || {}
  const minimumSample = readThreshold(
    thresholds,
    ['minimalna_proba', 'min_proba', 'minimum_sample'],
    20,
  )
  const minimumCompleteness = readThreshold(
    thresholds,
    ['minimalna_kompletnosc_proc', 'min_kompletnosc_proc', 'minimum_completeness_pct'],
    70,
  )
  const minimumDays = readThreshold(
    thresholds,
    ['minimalne_dni_serwisu', 'min_dni_serwisu', 'minimum_service_days'],
    4,
  )

  useEffect(() => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
    decisionKeysRef.current.clear()
    setSimulations({})
    setSimulationErrors({})
    setDecisionErrors({})
    setBusyByHash({})
    setLocalDecisions({})
  }, [contextKey])

  useEffect(() => () => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
  }, [])

  const setBusy = (hash, value) => {
    setBusyByHash((current) => {
      const next = { ...current }
      if (value) next[hash] = value
      else delete next[hash]
      return next
    })
  }

  const beginRequest = (hash, kind) => {
    controllersRef.current.get(hash)?.abort()
    const controller = new AbortController()
    controllersRef.current.set(hash, controller)
    setBusy(hash, kind)
    return controller
  }

  const finishRequest = (hash, controller) => {
    if (controllersRef.current.get(hash) !== controller) return
    controllersRef.current.delete(hash)
    setBusy(hash, null)
  }

  const runSimulation = async (candidate) => {
    const hash = candidate?.hash
    if (!hash || !rangeReady(range) || busyByHash[hash]) return
    const controller = beginRequest(hash, 'simulation')
    setSimulationErrors((current) => ({ ...current, [hash]: null }))
    setDecisionErrors((current) => ({ ...current, [hash]: null }))
    try {
      const result = await api(
        `/analityka/rezerwacje/rekomendacje/${encodeURIComponent(hash)}/symulacja`,
        'POST',
        { start: range.start, end: range.end },
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      setSimulations((current) => ({ ...current, [hash]: result }))
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      setSimulationErrors((current) => ({
        ...current,
        [hash]: error?.message || 'Nie udało się policzyć wpływu rekomendacji.',
      }))
    } finally {
      finishRequest(hash, controller)
    }
  }

  const decide = async (candidate, decision) => {
    const hash = candidate?.hash
    const simulation = simulations[hash]
    if (
      !hash
      || !canDecide
      || !rangeReady(range)
      || !simulation?.simulation_hash
      || busyByHash[hash]
    ) return

    const accepted = decision === 'accepted'
    const reason = accepted
      ? ACCEPT_REASON
      : (rejectReasons[hash] || DEFAULT_REJECT_REASON)
    const serviceName = candidate.serwis?.nazwa || 'wybranego serwisu'
    const approved = await confirm(
      accepted
        ? `Przyjąć zmianę czasu wizyty z ${formatMinutes(candidate.obecnie_min)} na ${formatMinutes(candidate.proponowane_min)} dla serwisu „${serviceName}” i grupy ${segmentLabel(candidate.segment)}? Zmiana obejmie wyłącznie nowe oceny dostępności.`
        : `Odrzucić rekomendację dla serwisu „${serviceName}” i pozostawić ${formatMinutes(candidate.obecnie_min)} dla grupy ${segmentLabel(candidate.segment)}? Decyzja zostanie zapisana.`,
      {
        title: accepted ? 'Przyjąć rekomendację?' : 'Odrzucić rekomendację?',
        confirmText: accepted ? 'Przyjmij zmianę' : 'Odrzuć rekomendację',
        cancelText: 'Wróć do symulacji',
        danger: !accepted,
      },
    )
    if (!approved) return

    const fingerprint = [
      hash,
      range.start,
      range.end,
      simulation.simulation_hash,
      decision,
      reason,
    ].join(':')
    let idempotencyKey = decisionKeysRef.current.get(fingerprint)
    if (!idempotencyKey) {
      idempotencyKey = nowyKluczIdempotencji('reservation-recommendation-decision')
      decisionKeysRef.current.set(fingerprint, idempotencyKey)
    }

    const controller = beginRequest(hash, decision)
    setDecisionErrors((current) => ({ ...current, [hash]: null }))
    try {
      const result = await api(
        `/analityka/rezerwacje/rekomendacje/${encodeURIComponent(hash)}/decyzja`,
        'POST',
        {
          start: range.start,
          end: range.end,
          simulation_hash: simulation.simulation_hash,
          decyzja: decision,
          powod: reason,
        },
        {
          signal: controller.signal,
          headers: { 'Idempotency-Key': idempotencyKey },
        },
      )
      if (controller.signal.aborted) return
      setLocalDecisions((current) => ({ ...current, [hash]: decision }))
      if (typeof onChanged === 'function') {
        try {
          Promise.resolve(onChanged(result)).catch(() => {})
        } catch {
          // Decyzja jest już zapisana; błąd odświeżenia rodzica nie może jej cofnąć.
        }
      }
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      setDecisionErrors((current) => ({
        ...current,
        [hash]: error?.message || 'Nie udało się zapisać decyzji.',
      }))
    } finally {
      finishRequest(hash, controller)
    }
  }

  if (!data) {
    return (
      <section aria-labelledby="reservation-recommendations-unavailable" className="space-y-4">
        <div>
          <h3 id="reservation-recommendations-unavailable" className="text-lg font-semibold text-ink">
            Rekomendacje
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
            Lokalo pokazuje zmianę dopiero po zebraniu wiarygodnej próby i nigdy nie stosuje jej automatycznie.
          </p>
        </div>
        <Banner variant="info">Rekomendacje są chwilowo niedostępne dla tego okresu.</Banner>
      </section>
    )
  }

  return (
    <section aria-labelledby="reservation-recommendations-title" className="space-y-5">
      <div>
        <h3 id="reservation-recommendations-title" className="text-lg font-semibold text-ink">
          Rekomendacje
        </h3>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
          Najpierw dowody, potem symulacja i Twoja decyzja. Lokalo nie zmienia reguł automatycznie.
        </p>
      </div>

      {!rangeReady(range) ? (
        <Banner variant="warn">Wybierz poprawny zakres dat, aby sprawdzić wpływ rekomendacji.</Banner>
      ) : null}

      {!candidates.length ? (
        <div className="border-y border-line py-8 text-center">
          <p className="font-semibold text-ink">Brak rekomendacji do decyzji</p>
          <p className="mx-auto mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Kandydat pojawi się po zebraniu co najmniej {minimumSample} pełnych pomiarów,
            {' '}{minimumCompleteness}% kompletności i danych z {minimumDays} dni serwisu.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-line border-y border-line">
          {candidates.map((candidate, index) => {
            const hash = candidate.hash
            const serviceName = candidate.serwis?.nazwa || `Serwis ${candidate.serwis?.id || ''}`.trim()
            const state = decisionFor(candidate, data.decyzje, localDecisions)
            const simulation = simulations[hash]
            const simulationError = simulationErrors[hash]
            const decisionError = decisionErrors[hash]
            const busy = busyByHash[hash]
            const headingId = `reservation-recommendation-${String(hash || index).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 24)}`

            return (
              <article key={hash || `${candidate.serwis?.id}:${candidate.segment}:${index}`} className="py-6" aria-labelledby={headingId}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h4 id={headingId} className="break-words font-semibold text-ink">
                      {serviceName} · grupa {segmentLabel(candidate.segment)}
                    </h4>
                    <p className="mt-1 text-sm leading-relaxed text-muted">
                      Propozycja czasu wizyty na podstawie pełnych pomiarów z wybranego okresu.
                    </p>
                  </div>
                  <span className={`self-start rounded-full border px-3 py-1 text-xs font-semibold ${
                    state === 'accepted'
                      ? 'border-success/30 bg-success/10 text-success'
                      : state === 'rejected'
                        ? 'border-line bg-white/[0.04] text-muted'
                        : 'border-line bg-white/[0.04] text-ink'
                  }`}>
                    {state === 'accepted' ? 'Przyjęta' : state === 'rejected' ? 'Odrzucona' : 'Do decyzji'}
                  </span>
                </div>

                <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3">
                  <EvidenceFact
                    label="Pełne pomiary"
                    value={`${candidate.proba ?? 0}/${minimumSample}`}
                    detail="próg minimalnej próby"
                  />
                  <EvidenceFact
                    label="Kompletność"
                    value={`${candidate.kompletnosc_proc ?? 0}%`}
                    detail={`wymagane min. ${minimumCompleteness}%`}
                  />
                  <EvidenceFact
                    label="Dni serwisu"
                    value={`${candidate.dni_serwisu ?? 0}/${minimumDays}`}
                    detail="różne dni z pomiarem"
                  />
                </dl>

                <div className="mt-5 flex flex-col gap-3 border-y border-line py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold text-muted">Proponowana zmiana</p>
                    <p className="mt-1 text-lg font-semibold tabular-nums text-ink">
                      {formatMinutes(candidate.obecnie_min)}
                      <span className="mx-2 text-muted" aria-hidden="true">→</span>
                      <span className="text-mint">{formatMinutes(candidate.proponowane_min)}</span>
                    </p>
                  </div>
                  {state === 'pending' && !simulation ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => runSimulation(candidate)}
                      loading={busy === 'simulation'}
                      loadingLabel="Liczę wpływ…"
                      disabled={!hash || !rangeReady(range) || Boolean(busy)}
                    >
                      <Icon name="search" className="h-4 w-4" />
                      Sprawdź wpływ
                    </Button>
                  ) : null}
                </div>

                {state === 'accepted' ? (
                  <Banner variant="success" className="mt-5">
                    Rekomendacja została przyjęta. Zmiana dotyczy nowych ocen dostępności;
                    istniejące rezerwacje pozostały bez zmian.
                  </Banner>
                ) : null}

                {state === 'rejected' ? (
                  <Banner variant="info" className="mt-5">
                    Rekomendacja została odrzucona. Obecna reguła pozostaje bez zmian.
                  </Banner>
                ) : null}

                {state === 'pending' && simulationError ? (
                  <Banner variant="danger" className="mt-5">
                    <div>
                      <p role="alert">{simulationError}</p>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-3"
                        onClick={() => runSimulation(candidate)}
                        loading={busy === 'simulation'}
                        loadingLabel="Liczę ponownie…"
                        disabled={Boolean(busy)}
                      >
                        Ponów symulację
                      </Button>
                    </div>
                  </Banner>
                ) : null}

                {state === 'pending' && simulation ? (
                  <div className="mt-5 space-y-5">
                    <SimulationSummary simulation={simulation} />

                    {!canDecide ? (
                      <Banner variant="info">
                        Możesz sprawdzać wpływ. Przyjęcie lub odrzucenie wymaga uprawnienia
                        do konfiguracji reguł rezerwacji.
                      </Banner>
                    ) : (
                      <>
                        <label className="block sm:max-w-md">
                          <span className="field-label">Powód odrzucenia</span>
                          <select
                            className="field mt-1.5 min-h-11 w-full"
                            value={rejectReasons[hash] || DEFAULT_REJECT_REASON}
                            onChange={(event) => setRejectReasons((current) => ({
                              ...current,
                              [hash]: event.target.value,
                            }))}
                            disabled={Boolean(busy)}
                          >
                            {REJECT_REASONS.map((reason) => (
                              <option key={reason.value} value={reason.value}>{reason.label}</option>
                            ))}
                          </select>
                        </label>

                        {decisionError ? (
                          <Banner variant="danger">
                            <div className="flex flex-col items-start gap-3">
                              <p role="alert">{decisionError}</p>
                              {typeof onChanged === 'function' ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    try {
                                      Promise.resolve(onChanged()).catch(() => {})
                                    } catch {
                                      // Rodzic pokaże własny stan błędu odświeżenia.
                                    }
                                  }}
                                >
                                  Odśwież rekomendacje
                                </Button>
                              ) : null}
                            </div>
                          </Banner>
                        ) : null}

                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                          <Button
                            variant="subtle"
                            size="sm"
                            onClick={() => decide(candidate, 'rejected')}
                            loading={busy === 'rejected'}
                            loadingLabel="Zapisuję odrzucenie…"
                            disabled={Boolean(busy)}
                          >
                            Odrzuć rekomendację
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => decide(candidate, 'accepted')}
                            loading={busy === 'accepted'}
                            loadingLabel="Przyjmuję zmianę…"
                            disabled={Boolean(busy)}
                          >
                            Przyjmij zmianę
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
