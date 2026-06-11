import { useState } from 'react'
import Zeszyt from './Zeszyt'
import RozliczenieDnia from './RozliczenieDnia'

// Admin: jedna zakładka „Zeszyt" z przełącznikiem na szczegółowe „Rozliczenie dnia".
export default function ZeszytPanel() {
  const [tryb, setTryb] = useState('zeszyt')
  const btn = (v, l) => (
    <button
      onClick={() => setTryb(v)}
      className={`rounded-xl px-4 py-2 text-sm font-bold transition ${
        tryb === v ? 'bg-accent-gradient text-bg shadow-glow' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
      }`}
    >
      {l}
    </button>
  )
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {btn('zeszyt', 'Zeszyt')}
        {btn('rozliczenie', 'Rozliczenie dnia')}
      </div>
      {tryb === 'zeszyt' ? <Zeszyt /> : <RozliczenieDnia />}
    </div>
  )
}
