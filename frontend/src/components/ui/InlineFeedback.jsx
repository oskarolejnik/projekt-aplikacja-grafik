export function InlineFeedback({ pending, feedback, className = '' }) {
  const isError = feedback?.type === 'error'
  const isWarning = feedback?.type === 'warning'

  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live="polite"
      className={`min-h-5 text-xs ${isError ? 'text-danger' : isWarning ? 'text-lemon' : feedback?.type === 'success' ? 'text-success' : 'text-muted'} ${className}`}
    >
      {pending || feedback?.message || ''}
    </div>
  )
}
