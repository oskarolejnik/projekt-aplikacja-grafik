import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { pushWspierany, wlaczPowiadomienia } from '../lib/push'
import EmployeeAvailability from './EmployeeAvailability'
import EmployeeSchedule from './EmployeeSchedule'
import { motion, AnimatePresence } from 'framer-motion'
import { PillSwitch } from '../components/ui/PillSwitch'

const LAST_SEEN_KEY = 'grafik_ostatni_grafik'

// Powłoka obszaru pracownika: wspólny nagłówek + przełącznik dwóch widoków
// („Moja dyspozycyjność" / „Mój grafik"), powiadomienia i przycisk push. Mobile-first.
export default function EmployeeArea() {
  const { user, logout } = useAuth()
  const { week } = useData()
  const { toast } = useToast()
  const [widok, setWidok] = useState('dyspozycyjnosc')
  const [nowyGrafik, setNowyGrafik] = useState(false)
  const [pushOn, setPushOn] = useState(false)

  const imie = user?.imie || user?.login

  // Wykryj nowo udostępniony grafik -> baner + odznaka na zakładce „Mój grafik".
  useEffect(() => {
    let off = false
    const [s, e] = week.split('|')
    api(`/me/grafik?start=${s}&end=${e}`)
      .then((r) => {
        if (off) return
        if (r.opublikowany && r.opublikowano_at && localStorage.getItem(LAST_SEEN_KEY) !== r.opublikowano_at) {
          setNowyGrafik(true)
          toast('Nowy grafik został udostępniony!', 'success')
        }
      })
      .catch(() => {})
    return () => {
      off = true
    }
  }, [week, toast])

  const oznaczWidziany = useCallback((ts) => {
    localStorage.setItem(LAST_SEEN_KEY, ts)
    setNowyGrafik(false)
  }, [])

  const enablePush = async () => {
    try {
      await wlaczPowiadomienia()
      setPushOn(true)
      toast('Powiadomienia włączone.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const zmienWidok = (v) => {
    setWidok(v)
    if (v === 'grafik') setNowyGrafik(false)
  }

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-2xl transform-gpu" />

      <header className="relative z-10 flex items-center justify-between border-b border-line bg-bg-2/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">Rajcula</h1>
            <p className="text-xs text-muted">Cześć, {imie}!</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {pushWspierany() && !pushOn && (
            <button
              onClick={enablePush}
              title="Włącz powiadomienia"
              className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
            >
              <Icon name="bell" className="h-4 w-4" />
              <span className="hidden md:inline">Powiadomienia</span>
            </button>
          )}
          <button
            onClick={logout}
            className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden sm:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-3xl px-4 py-6 pb-safe md:py-10">
        {/* Pill Switcher: gradientowa pigułka „podróżuje" pod aktywną zakładką (layoutId + sprężyna). */}
        <PillSwitch
          className="mb-6"
          layoutId="empTab"
          value={widok}
          onChange={zmienWidok}
          options={[
            { value: 'dyspozycyjnosc', label: 'Moja dyspozycyjność' },
            { value: 'grafik', label: 'Mój grafik', badge: nowyGrafik },
          ]}
        />

        {/* Treść zakładki: miękki crossfade (Framer). Kierunkowość daje sama wędrująca pigułka. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={widok}
            initial={{ opacity: 0, scale: 0.97, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.985, y: -8, transition: { duration: 0.16, ease: 'easeIn' } }}
            transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
          >
            {widok === 'dyspozycyjnosc' ? <EmployeeAvailability /> : <EmployeeSchedule onSeen={oznaczWidziany} />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
