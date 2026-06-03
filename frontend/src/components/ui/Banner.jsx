import { Icon } from '../../lib/icons'

const STYLES = {
  info: 'border-info/30 bg-info/10 text-info',
  warn: 'border-lemon/30 bg-lemon/10 text-lemon',
  success: 'border-success/30 bg-success/10 text-success',
  danger: 'border-danger/30 bg-danger/10 text-danger',
}
const ICONS = { info: 'info', warn: 'warning', success: 'check', danger: 'warning' }

export function Banner({ variant = 'info', className = '', children }) {
  return (
    <div className={`flex items-start gap-3 rounded-xl border p-4 text-sm ${STYLES[variant]} ${className}`}>
      <Icon name={ICONS[variant]} className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="leading-relaxed">{children}</div>
    </div>
  )
}
