import { Component } from 'react'

export function LazyFallback({ compact = false, label = 'Ładowanie widoku' }) {
  return (
    <div
      className={compact
        ? 'min-h-[18rem] w-full py-2'
        : 'grid min-h-dvh place-items-center bg-bg px-5 py-8'}
    >
      <span className="sr-only" role="status" aria-live="polite">{label}</span>
      <div
        aria-hidden="true"
        className={`w-full animate-pulse ${compact ? '' : 'max-w-4xl'}`}
      >
        <div className="mb-6 h-6 w-40 rounded-lg bg-white/[0.08]" />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="h-44 rounded-2xl border border-line bg-white/[0.03]" />
          <div className="h-44 rounded-2xl border border-line bg-white/[0.03]" />
        </div>
        <div className="mt-4 h-20 rounded-2xl border border-line bg-white/[0.03]" />
      </div>
    </div>
  )
}

function reloadApplication() {
  window.location.reload()
}

export class LazyErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidUpdate(previousProps) {
    if (this.state.error && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  handleRetry = () => {
    if (!this.props.onRetry) {
      const reload = this.props.reload || reloadApplication
      reload()
      return
    }

    this.props.onRetry()
    this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children

    const { fullPage = false, onRetry, reload = reloadApplication } = this.props
    return (
      <div className={fullPage ? 'grid min-h-dvh place-items-center bg-bg px-5 py-8' : 'min-h-[18rem] py-2'}>
        <div
          role="alert"
          className="w-full max-w-xl rounded-2xl border border-line bg-white/[0.03] p-6 shadow-soft md:p-8"
        >
          <h2 className="font-display text-lg font-semibold text-ink">Nie udało się wczytać widoku</h2>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">
            Połączenie mogło zostać przerwane albo dostępna jest nowsza wersja aplikacji.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onRetry ? reload : this.handleRetry}
              className="min-h-11 rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-bg transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
            >
              Odśwież aplikację
            </button>
            {onRetry && (
              <button
                type="button"
                onClick={this.handleRetry}
                className="min-h-11 rounded-xl border border-line bg-white/[0.04] px-4 py-2 text-sm font-semibold text-muted transition hover:bg-white/[0.08] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
              >
                Spróbuj ponownie
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }
}
