import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../lib/api'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'

const TIMEOUTS = [
  { value: 180, label: '3 minuty' },
  { value: 300, label: '5 minut' },
  { value: 600, label: '10 minut' },
  { value: 900, label: '15 minut' },
]

export default function WorkstationSetup() {
  const { logout } = useAuth()
  const [stations, setStations] = useState([])
  const [name, setName] = useState('Recepcja')
  const [idleTimeout, setIdleTimeout] = useState(300)
  const [currentStation, setCurrentStation] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = () => api('/reservation-workstations')
    .then((items) => setStations(Array.isArray(items) ? items : []))
    .catch(() => setStations([]))

  useEffect(() => {
    void refresh()
    void api(
      '/reservation-workstations/operators',
      'GET',
      null,
      { sessionHandling: false },
    ).then((gate) => {
      if (gate?.station) setCurrentStation(gate.station)
    }).catch(() => null)
  }, [])

  const register = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const station = await api('/reservation-workstations', 'POST', {
        name: name.trim(),
        idle_timeout_seconds: Number(idleTimeout),
      })
      setCurrentStation(station)
      setStations((items) => [station, ...items.filter((item) => item.id !== station.id)])
    } catch (caught) {
      setError(caught?.message || 'Nie udało się przygotować stanowiska.')
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (station) => {
    if (!window.confirm(`Wyłączyć stanowisko „${station.name}”?`)) return
    setBusy(true)
    setError('')
    try {
      await api(`/reservation-workstations/${station.id}`, 'DELETE')
      setStations((items) => items.map((item) => (
        item.id === station.id ? { ...item, active: false } : item
      )))
      if (currentStation?.id === station.id) setCurrentStation(null)
    } catch (caught) {
      setError(caught?.message || 'Nie udało się wyłączyć stanowiska.')
    } finally {
      setBusy(false)
    }
  }

  const openWorkstation = () => {
    logout()
    window.location.assign(`${window.location.pathname}?stanowisko`)
  }

  return (
    <section className="rounded-2xl border border-line bg-white/[0.025] p-5 sm:p-6" aria-labelledby="workstation-setup-title">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Recepcja / Host</p>
          <h3 id="workstation-setup-title" className="mt-1 font-display text-lg font-semibold text-ink">Tryb stanowiska</h3>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
            Przypisz ten komputer do recepcji. Operatorzy przełączają się własnym PIN-em, bez dostępu do ustawień administratora.
          </p>
        </div>
        {currentStation ? (
          <Button type="button" size="sm" onClick={openWorkstation}>Otwórz stanowisko</Button>
        ) : null}
      </div>

      {error ? <Banner variant="danger" className="mt-4">{error}</Banner> : null}
      {currentStation ? (
        <Banner variant="success" className="mt-4">
          Ten komputer jest gotowy jako „{currentStation.name}”. Ustaw PIN-y operatorów w zakładce Konta pracowników.
        </Banner>
      ) : (
        <form className="mt-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem_auto] md:items-end" onSubmit={register}>
          <label className="block text-sm font-medium text-ink">
            Nazwa stanowiska
            <input
              className="field mt-2 min-h-11 w-full"
              value={name}
              maxLength={96}
              required
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-ink">
            Blokada po bezczynności
            <select
              className="field mt-2 min-h-11 w-full"
              value={idleTimeout}
              onChange={(event) => setIdleTimeout(Number(event.target.value))}
            >
              {TIMEOUTS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <Button type="submit" loading={busy} disabled={!name.trim()} loadingLabel="Przygotowuję…">
            Ustaw ten komputer
          </Button>
        </form>
      )}

      {stations.some((station) => station.active) ? (
        <details className="group mt-5 border-t border-line pt-4">
          <summary className="min-h-11 cursor-pointer list-none py-2 text-sm font-semibold text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
            Aktywne stanowiska ({stations.filter((station) => station.active).length})
          </summary>
          <div className="mt-2 divide-y divide-line rounded-xl border border-line">
            {stations.filter((station) => station.active).map((station) => (
              <div key={station.id} className="flex min-h-14 items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{station.name}</p>
                  <p className="text-xs text-muted">Blokada po {Math.round(station.idle_timeout_seconds / 60)} min</p>
                </div>
                <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => revoke(station)}>
                  Wyłącz
                </Button>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  )
}
