import { useState } from 'react'
import { PillSwitch } from '../ui/PillSwitch'
import Grafik from './Grafik'
import Wymagania from './Wymagania'
import Dyspozycje from './Dyspozycje'

const WIDOKI = [
  { value: 'grafik', label: 'Grafik', Comp: Grafik },
  { value: 'plan', label: 'Plan obsady', Comp: Wymagania },
  { value: 'dyspozycje', label: 'Dyspozycje', Comp: Dyspozycje },
]

// Jedno stanowisko planowania: satelity grafiku pozostają dostępne kontekstowo,
// ale nie zajmują osobnych pozycji w globalnej nawigacji administratora.
export default function GrafikWorkspace() {
  const [widok, setWidok] = useState('grafik')
  const [zamontowane, setZamontowane] = useState(['grafik'])

  const pokazWidok = (next) => {
    setZamontowane((lista) => (lista.includes(next) ? lista : [...lista, next]))
    setWidok(next)
  }

  return (
    <div className="space-y-6">
      <PillSwitch
        className="mx-auto w-full max-w-xl"
        label="Obszar planowania grafiku"
        value={widok}
        onChange={pokazWidok}
        options={WIDOKI.map(({ value, label }) => ({ value, label }))}
      />
      {WIDOKI.filter(({ value }) => zamontowane.includes(value)).map(({ value, label, Comp }) => {
        const aktywny = value === widok

        return (
          <section
            key={value}
            role="region"
            aria-label={label}
            hidden={!aktywny}
            className={aktywny ? 'animate-tab-in' : undefined}
          >
            <Comp active={aktywny} />
          </section>
        )
      })}
    </div>
  )
}
