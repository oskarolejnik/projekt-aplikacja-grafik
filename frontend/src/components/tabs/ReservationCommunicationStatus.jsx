import { Icon } from '../../lib/icons'

const STATE_META = {
  queued: { label: 'W kolejce', icon: 'clock', className: 'border-line bg-white/[0.04] text-muted' },
  processing: { label: 'Wysyłanie', icon: 'refresh', className: 'border-mint/25 bg-mint/10 text-mint' },
  retry: { label: 'Ponowienie zaplanowane', icon: 'clock', className: 'border-lemon/30 bg-lemon/10 text-lemon' },
  sent: { label: 'Wysłano', icon: 'check', className: 'border-success/25 bg-success/10 text-success' },
  failed: { label: 'Nie dostarczono', icon: 'warning', className: 'border-danger/30 bg-danger/10 text-danger' },
  uncertain: { label: 'Sprawdź wynik', icon: 'warning', className: 'border-lemon/30 bg-lemon/10 text-lemon' },
  expired: { label: 'Wiadomość wygasła', icon: 'warning', className: 'border-danger/30 bg-danger/10 text-danger' },
  cancelled: { label: 'Anulowano', icon: 'close', className: 'border-line bg-white/[0.03] text-muted' },
}

const CHANNEL_LABELS = {
  email: 'e-mail',
  sms: 'SMS',
  oba: 'e-mail + SMS',
}

export function communicationStateMeta(state) {
  return STATE_META[state] || {
    label: state ? 'Status nieznany' : 'Brak wiadomości',
    icon: 'info',
    className: 'border-line bg-white/[0.03] text-muted',
  }
}

export default function ReservationCommunicationStatus({
  summary,
  showChannel = true,
  live = false,
  className = '',
}) {
  const meta = communicationStateMeta(summary?.state)
  const channel = showChannel ? CHANNEL_LABELS[summary?.channel] : null
  const attentionCount = Number(summary?.attention_count) || 0
  const attentionText = attentionCount === 1
    ? ', 1 wiadomość wymaga uwagi'
    : attentionCount > 1
      ? `, ${attentionCount} wiadomości wymagają uwagi`
      : ''

  return (
    <span
      role={live ? 'status' : undefined}
      aria-label={`${meta.label}${channel ? `, ${channel}` : ''}${attentionText}`}
      className={`inline-flex min-h-7 max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold leading-none ${meta.className} ${className}`}
    >
      <Icon name={meta.icon} className={`h-3.5 w-3.5 shrink-0 ${summary?.state === 'processing' ? 'animate-spin motion-reduce:animate-none' : ''}`} />
      <span className="truncate">{meta.label}</span>
      {channel ? <span className="shrink-0 font-medium opacity-75">· {channel}</span> : null}
      {attentionCount > 0 ? <span className="shrink-0 font-medium opacity-80">· {attentionCount}</span> : null}
    </span>
  )
}
