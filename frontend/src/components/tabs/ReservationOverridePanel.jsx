import { useEffect, useId, useState } from 'react'
import { Icon } from '../../lib/icons'
import { Button } from '../ui/Button'

export const OVERRIDE_REASONS = [
  { value: 'operational_decision', label: 'Decyzja operacyjna managera' },
  { value: 'guest_request', label: 'Prośba gościa' },
  { value: 'large_group_confirmed', label: 'Potwierdzona duża grupa' },
  { value: 'event_exception', label: 'Wyjątek związany z wydarzeniem' },
  { value: 'walk_in', label: 'Goście bez rezerwacji' },
  { value: 'other', label: 'Inny powód' },
]

const violationsFrom = (availability) => availability?.violations
  || availability?.checks?.filter((check) => check.passed === false)
  || []

const scopeText = (scope) => {
  if (!scope) return null
  const room = scope.sala_nazwa || scope.room_name || (scope.sala_id ? `sala #${scope.sala_id}` : null)
  const channel = scope.kanal === 'online' ? 'online' : scope.kanal === 'wewnetrzna' ? 'telefon / obsługa' : null
  return [room, channel].filter(Boolean).join(' · ') || null
}

export default function ReservationOverridePanel({
  availability,
  value = { powod: '', notatka: '' },
  onChange,
  onConfirm,
  onCancel,
  busy = false,
  actionLabel = 'Zapisz mimo limitu',
  requiresPin = false,
  reauthError = null,
  retryAfter = 0,
}) {
  const headingId = useId()
  const pinHelpId = useId()
  const [pin, setPin] = useState('')
  const [retrySeconds, setRetrySeconds] = useState(() => Math.max(0, Number(retryAfter) || 0))
  const violations = violationsFrom(availability)
  const update = (patch) => onChange?.({ ...value, ...patch })
  const needsNote = value.powod === 'other'
  const pinValid = !requiresPin || /^\d{6}$/.test(pin)
  const valid = Boolean(value.powod)
    && (!needsNote || Boolean(value.notatka?.trim()))
    && pinValid
    && retrySeconds === 0

  useEffect(() => {
    setRetrySeconds(Math.max(0, Number(retryAfter) || 0))
  }, [retryAfter])

  useEffect(() => {
    if (retrySeconds <= 0) return undefined
    const timer = window.setTimeout(() => {
      setRetrySeconds((current) => Math.max(0, current - 1))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [retrySeconds])

  const confirmOverride = () => {
    if (!valid || busy) return
    const submittedPin = pin
    if (requiresPin) setPin('')
    const override = {
      powod: value.powod,
      notatka: value.notatka?.trim() || null,
      potwierdzone: true,
    }
    if (requiresPin) onConfirm?.(override, { pin: submittedPin })
    else onConfirm?.(override)
  }

  return (
    <section className="mt-4 rounded-xl border border-lemon/30 bg-lemon/[0.06] p-4" aria-labelledby={headingId}>
      <div className="flex items-start gap-3">
        <Icon name="warning" className="mt-0.5 h-5 w-5 shrink-0 text-lemon" />
        <div className="min-w-0">
          <h4 id={headingId} className="font-semibold text-ink">Ta operacja przekroczy ustawiony limit</h4>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {requiresPin
              ? 'Możesz kontynuować po podaniu powodu i potwierdzeniu decyzji własnym PIN-em. Decyzja zostanie zapisana w audycie rezerwacji.'
              : 'Możesz kontynuować po podaniu powodu. Decyzja zostanie zapisana w audycie rezerwacji.'}
          </p>
        </div>
      </div>

      {violations.length ? (
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {violations.map((violation, index) => (
            <li key={`${violation.code || violation.rule}-${index}`} className="py-3 text-sm">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                <span className="min-w-0 break-words font-medium text-ink">{violation.message || violation.rule || 'Przekroczony limit'}</span>
                {scopeText(violation.scope) ? <span className="break-words text-xs text-muted sm:shrink-0 sm:text-right">{scopeText(violation.scope)}</span> : null}
              </div>
              {violation.limit != null ? (
                <p className="mt-1 break-words text-xs text-muted">
                  Limit: {violation.limit} · teraz: {violation.observed ?? '—'} · po operacji: {violation.projected ?? '—'}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="field-label">
          Powód przekroczenia
          <select
            value={value.powod || ''}
            onChange={(event) => update({ powod: event.target.value })}
            className="field mt-1.5 min-h-11 normal-case tracking-normal"
            disabled={busy}
            required
          >
            <option value="">Wybierz powód</option>
            {OVERRIDE_REASONS.map((reason) => <option key={reason.value} value={reason.value}>{reason.label}</option>)}
          </select>
        </label>
        <label className="field-label">
          Notatka {needsNote ? '(wymagana)' : '(opcjonalnie)'}
          <textarea
            value={value.notatka || ''}
            onChange={(event) => update({ notatka: event.target.value })}
            rows={2}
            maxLength={240}
            className="field mt-1.5 min-h-11 resize-y normal-case tracking-normal"
            disabled={busy}
            required={needsNote}
            placeholder={needsNote ? 'Krótko opisz decyzję' : 'Dodatkowy kontekst dla zespołu'}
          />
        </label>
      </div>

      {requiresPin ? (
        <div className="mt-4 max-w-sm">
          <label className="field-label" htmlFor={`${pinHelpId}-input`}>
            Twój 6-cyfrowy PIN
          </label>
          <input
            id={`${pinHelpId}-input`}
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            autoComplete="off"
            name="workstation-reauth-pin"
            value={pin}
            onChange={(event) => setPin(event.target.value.replace(/\D/g, '').slice(0, 6))}
            className="field mt-1.5 min-h-11 tabular-nums tracking-[0.24em]"
            aria-describedby={pinHelpId}
            aria-invalid={Boolean(reauthError)}
            disabled={busy || retrySeconds > 0}
            required
          />
          <p id={pinHelpId} className={`mt-1.5 text-xs leading-relaxed ${reauthError ? 'text-danger' : 'text-muted'}`}>
            {reauthError
              ? <span role="alert">{reauthError}</span>
              : 'PIN potwierdza operatora tylko dla tej jednej decyzji i nie jest zapisywany.'}
            {retrySeconds > 0 ? ` Spróbuj ponownie za ${retrySeconds} s.` : ''}
          </p>
        </div>
      ) : null}

      <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel ? <Button variant="subtle" size="sm" onClick={onCancel} disabled={busy}>Wróć do edycji</Button> : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={confirmOverride}
          loading={busy}
          loadingLabel={requiresPin ? 'Potwierdzam operatora…' : 'Zapisuję decyzję…'}
          disabled={!valid || busy || retrySeconds > 0}
          className="border-lemon/30 text-lemon hover:bg-lemon/10"
        >
          <Icon name="warning" className="h-4 w-4" />
          {actionLabel}
        </Button>
      </div>
    </section>
  )
}
