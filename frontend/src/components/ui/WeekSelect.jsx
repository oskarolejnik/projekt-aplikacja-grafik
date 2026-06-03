import { useData } from '../../context/DataContext'
import { Icon } from '../../lib/icons'

// Wybór tygodnia roboczego (środa–wtorek). Współdzielony przez wszystkie zakładki.
export function WeekSelect({ className = '' }) {
  const { weeks, week, setWeek } = useData()
  return (
    <div className={`relative ${className}`}>
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
        <Icon name="calendar" className="h-4 w-4" />
      </span>
      <select
        value={week}
        onChange={(e) => setWeek(e.target.value)}
        aria-label="Wybierz tydzień"
        className="field min-w-[230px] cursor-pointer appearance-none pl-9 pr-9 font-semibold"
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
