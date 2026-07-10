import { useState } from 'react'
import { useData } from '../../context/DataContext'
import { Icon } from '../../lib/icons'

// Wybór okresu grafiku (tydzień lub miesiąc — wg cyklu lokalu). Współdzielony przez zakładki.
export function WeekSelect({ className = '', beforeChange, disabled = false }) {
  const { weeks, week, setWeek } = useData()
  const [changing, setChanging] = useState(false)

  const handleChange = async (event) => {
    const nextWeek = event.target.value
    if (nextWeek === week || changing) return
    setChanging(true)
    try {
      const allowed = beforeChange ? await beforeChange(nextWeek, week) : true
      if (allowed !== false) setWeek(nextWeek)
    } finally {
      setChanging(false)
    }
  }

  return (
    <div className={`relative w-full min-w-0 sm:w-auto sm:shrink-0 ${className}`}>
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
        <Icon name="calendar" className="h-4 w-4" />
      </span>
      <select
        value={week}
        onChange={handleChange}
        disabled={disabled || changing}
        aria-busy={changing || undefined}
        aria-label="Wybierz okres grafiku"
        className="field w-full min-w-0 cursor-pointer appearance-none pl-9 pr-9 font-semibold sm:min-w-[280px]"
      >
        {weeks.map((w) => (
          <option key={w.value} value={w.value} className="bg-surface text-ink">
            {w.label}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
        <Icon name="chevronDown" className="h-4 w-4" />
      </span>
    </div>
  )
}
