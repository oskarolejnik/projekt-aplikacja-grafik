import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Button } from '../ui/Button'

function operatorId(operator) {
  return operator?.id ?? operator?.userId ?? operator?.user_id ?? null
}

function operatorName(operator) {
  if (operator?.name) return operator.name
  if (operator?.displayName) return operator.displayName
  if (operator?.display_name) return operator.display_name

  const fullName = [operator?.firstName ?? operator?.imie, operator?.lastName ?? operator?.nazwisko]
    .filter(Boolean)
    .join(' ')

  return fullName || operator?.login || 'Operator'
}

function operatorRole(operator) {
  return operator?.roleLabel ?? operator?.role ?? operator?.rola ?? ''
}

function sameId(first, second) {
  if (first == null || second == null) return first == null && second == null
  return String(first) === String(second)
}

function retrySeconds(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return 0
  return Math.ceil(parsed)
}

function formatCountdown(seconds) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

/**
 * Presentational workstation unlock gate. Session and API behavior stay in the parent.
 */
export function WorkstationGate({
  station,
  operators = [],
  currentOperatorId = null,
  busy = false,
  error = '',
  retryAfter = 0,
  onUnlock,
  onUsePassword,
  onForgetStation,
}) {
  const inputId = useId()
  const pinInputRef = useRef(null)
  const entries = useMemo(
    () => operators
      .map((operator) => ({
        id: operatorId(operator),
        name: operatorName(operator),
        role: operatorRole(operator),
      }))
      .filter((operator) => operator.id != null),
    [operators],
  )
  const entryIds = entries.map((operator) => String(operator.id)).join('|')
  const [selectedUserId, setSelectedUserId] = useState(() => (
    entries.find((operator) => sameId(operator.id, currentOperatorId))?.id ?? null
  ))
  const [pin, setPin] = useState('')
  const [localError, setLocalError] = useState('')
  const [secondsRemaining, setSecondsRemaining] = useState(() => retrySeconds(retryAfter))

  useEffect(() => {
    const currentOperator = entries.find((operator) => sameId(operator.id, currentOperatorId))
    setSelectedUserId((selected) => {
      if (currentOperator) return currentOperator.id
      return entries.some((operator) => sameId(operator.id, selected)) ? selected : null
    })
  }, [currentOperatorId, entryIds]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setPin('')
    setLocalError('')
    if (selectedUserId != null) pinInputRef.current?.focus()
  }, [selectedUserId])

  useEffect(() => {
    setSecondsRemaining(retrySeconds(retryAfter))
  }, [retryAfter])

  useEffect(() => {
    if (!error) return
    setPin('')
    pinInputRef.current?.focus()
  }, [error])

  useEffect(() => {
    if (secondsRemaining <= 0) return undefined
    const timer = window.setTimeout(() => {
      setSecondsRemaining((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [secondsRemaining])

  const externalError = typeof error === 'string' ? error : error?.message
  const visibleError = localError || externalError || ''
  const selectedOperator = entries.find((operator) => sameId(operator.id, selectedUserId))
  const pinHintId = `${inputId}-hint`
  const errorId = `${inputId}-error`

  const selectOperator = (userId) => {
    setSelectedUserId(userId)
  }

  const changePin = (event) => {
    setPin(event.target.value.replace(/\D/g, '').slice(0, 6))
    setLocalError('')
  }

  const submit = (event) => {
    event.preventDefault()
    if (busy || secondsRemaining > 0) return
    if (selectedUserId == null) {
      setLocalError('Wybierz operatora.')
      return
    }
    if (!/^\d{6}$/.test(pin)) {
      setLocalError('PIN musi mieć 6 cyfr.')
      pinInputRef.current?.focus()
      return
    }

    setLocalError('')
    onUnlock?.({ userId: selectedUserId, pin })
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-bg px-4 py-8 text-ink sm:px-6">
      <section
        className="card w-full max-w-lg p-6 sm:p-8"
        aria-labelledby={`${inputId}-title`}
      >
        <header>
          <p className="text-sm font-medium text-muted">
            {station?.name ? `Stanowisko · ${station.name}` : 'Stanowisko recepcji'}
          </p>
          <h1 id={`${inputId}-title`} className="mt-2 font-display text-2xl font-semibold tracking-tight">
            Wróć do pracy
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
            Wybierz swoje konto i wpisz PIN. Dane gości pozostają ukryte do odblokowania.
          </p>
        </header>

        <form className="mt-7" onSubmit={submit} noValidate>
          <fieldset disabled={busy}>
            <legend className="field-label">Operator</legend>
            {entries.length ? (
              <div className="mt-2 overflow-hidden rounded-2xl border border-line bg-white/[0.025]">
                {entries.map((operator, index) => {
                  const selected = sameId(operator.id, selectedUserId)
                  const current = sameId(operator.id, currentOperatorId)
                  return (
                    <label
                      key={String(operator.id)}
                      className={`block cursor-pointer ${index ? 'border-t border-line' : ''}`}
                    >
                      <input
                        className="peer sr-only"
                        type="radio"
                        name="workstation-operator"
                        value={String(operator.id)}
                        checked={selected}
                        onChange={() => selectOperator(operator.id)}
                      />
                      <span className="flex min-h-14 items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-white/[0.045] peer-checked:bg-mint/[0.10] peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-inset peer-focus-visible:ring-mint/70">
                        <span className="min-w-0">
                          <span className={`block break-words text-sm font-semibold ${selected ? 'text-mint' : 'text-ink'}`}>
                            {operator.name}
                          </span>
                          {operator.role ? <span className="mt-0.5 block text-xs text-muted">{operator.role}</span> : null}
                        </span>
                        {current ? <span className="shrink-0 text-xs font-medium text-muted">Ostatnio używane</span> : null}
                      </span>
                    </label>
                  )
                })}
              </div>
            ) : (
              <p className="mt-2 rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-sm text-muted">
                Brak operatorów przypisanych do tego stanowiska.
              </p>
            )}
          </fieldset>

          {selectedOperator ? (
            <div className="mt-6">
              <div className="flex items-baseline justify-between gap-3">
                <label htmlFor={`${inputId}-pin`} className="field-label">PIN</label>
                <span id={pinHintId} className="text-xs text-muted">6 cyfr</span>
              </div>
              <input
                ref={pinInputRef}
                id={`${inputId}-pin`}
                name="pin"
                type="password"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="off"
                maxLength={6}
                value={pin}
                onChange={changePin}
                disabled={busy}
                aria-invalid={visibleError ? 'true' : undefined}
                aria-describedby={`${pinHintId}${visibleError ? ` ${errorId}` : ''}`}
                className="field mt-2 min-h-12 w-full text-center text-xl tracking-[0.35em] disabled:cursor-wait disabled:opacity-60"
              />
            </div>
          ) : null}

          {visibleError ? (
            <p id={errorId} className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
              {visibleError}
            </p>
          ) : null}

          {secondsRemaining > 0 ? (
            <p className="mt-3 text-sm text-muted">
              Kolejna próba za <span className="font-semibold tabular-nums text-ink">{formatCountdown(secondsRemaining)}</span>.
            </p>
          ) : null}

          <div className="mt-6 grid gap-3">
            <Button
              type="submit"
              className="w-full"
              disabled={!selectedOperator || secondsRemaining > 0}
              loading={busy}
              loadingLabel="Odblokowuję…"
            >
              Odblokuj
            </Button>
            <Button type="button" variant="ghost" className="w-full" onClick={onUsePassword} disabled={busy}>
              Zaloguj się hasłem
            </Button>
          </div>
        </form>

        {onForgetStation ? (
          <button
            type="button"
            onClick={onForgetStation}
            disabled={busy}
            className="mt-5 min-h-11 w-full rounded-xl px-3 text-sm font-medium text-muted transition-colors hover:bg-white/[0.04] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/70 disabled:opacity-50"
          >
            Usuń powiązanie stanowiska
          </button>
        ) : null}
      </section>
    </main>
  )
}

export default WorkstationGate
