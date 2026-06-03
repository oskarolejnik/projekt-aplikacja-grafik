import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { WeekSelect } from '../components/ui/WeekSelect'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { ddmmyyyy, hhmm, NAZWY_DNI, zakresDni } from '../lib/format'

// Samoobsługa pracownika: zgłaszanie dyspozycyjności na wybrany tydzień.
// Zastępuje import CSV — dane trafiają wprost do tabeli Dyspozycja (pod kontem).
export default function EmployeeAvailability() {
  const { user, logout } = useAuth()
  const { week } = useData()
  const { toast } = useToast()
  const [dni, setDni] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [s, e] = week.split('|')
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const existing = await api(`/me/dyspozycje?start=${s}&end=${e}`)
      const map = Object.fromEntries(existing.map((d) => [d.data, d]))
      setDni(
        daty.map((d) => {
          const rec = map[d]
          return {
            data: d,
            dostepnosc: rec ? rec.dostepnosc : true, // domyślnie dostępny
            od: rec && rec.godz_od ? hhmm(rec.godz_od) : '',
          }
        }),
      )
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [s, e, daty, toast])

  useEffect(() => {
    load()
  }, [load])

  const setDay = (idx, patch) => setDni((cur) => cur.map((d, i) => (i === idx ? { ...d, ...patch } : d)))

  const zapisz = async () => {
    setSaving(true)
    try {
      await api('/me/dyspozycje', 'PUT', {
        dyspozycje: dni.map((d) => ({
          data: d.data,
          dostepnosc: d.dostepnosc,
          godz_od: d.dostepnosc && d.od ? `${d.od}:00` : null,
        })),
      })
      toast('Zapisano Twoją dyspozycyjność.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const imie = user?.imie || user?.login

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-3xl" />

      {/* Górny pasek */}
      <header className="relative z-10 flex h-20 items-center justify-between border-b border-line bg-bg-2/60 px-5 backdrop-blur md:px-10">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent-gradient text-bg">
            <Icon name="calendar" className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">Moja dyspozycyjność</h1>
            <p className="text-xs text-muted">Cześć, {imie}!</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
        >
          <Icon name="logout" className="h-4 w-4" />
          <span className="hidden sm:inline">Wyloguj</span>
        </button>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-3xl px-5 py-8 md:py-10">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <WeekSelect />
          <span className="text-sm text-muted">Zaznacz dni i godziny, w których możesz pracować.</span>
        </div>

        <Card className="p-6">
          {loading ? (
            <div className="grid place-items-center py-16">
              <Spinner className="h-6 w-6 text-muted" />
            </div>
          ) : (
            <div className="space-y-3">
              {dni.map((d, i) => (
                <div key={d.data} className="flex flex-col gap-3 rounded-xl border border-line bg-white/[0.02] p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-[150px]">
                    <div className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d.data).getDay()]}</div>
                    <div className="text-xs text-muted">{ddmmyyyy(d.data)}</div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex overflow-hidden rounded-lg border border-line">
                      <button
                        onClick={() => setDay(i, { dostepnosc: true })}
                        className={`px-4 py-2 text-xs font-bold transition ${d.dostepnosc ? 'bg-success text-bg' : 'text-muted hover:text-ink'}`}
                      >
                        Dostępny
                      </button>
                      <button
                        onClick={() => setDay(i, { dostepnosc: false })}
                        className={`px-4 py-2 text-xs font-bold transition ${!d.dostepnosc ? 'bg-danger text-white' : 'text-muted hover:text-ink'}`}
                      >
                        Niedostępny
                      </button>
                    </div>

                    <label className="flex items-center gap-2 text-xs text-muted">
                      <span className="hidden sm:inline">od</span>
                      <input
                        type="time"
                        value={d.od}
                        onChange={(ev) => setDay(i, { od: ev.target.value })}
                        disabled={!d.dostepnosc}
                        className="field w-28 px-2 py-2 disabled:opacity-40"
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={zapisz}
            disabled={saving || loading}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-cream px-6 py-3.5 text-sm font-bold uppercase tracking-[0.15em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98] disabled:opacity-60"
          >
            {saving ? <Spinner className="h-4 w-4" /> : <Icon name="check" className="h-4 w-4" />}
            {saving ? 'Zapisywanie…' : 'Zapisz dyspozycyjność'}
          </button>
        </Card>
      </main>
    </div>
  )
}
