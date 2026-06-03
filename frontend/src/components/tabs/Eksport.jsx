import { useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { API } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Eksport grafiku do CSV (tabela przestawna pracownik × dzień). Pobieranie pliku
// przez nawigację do endpointu — zachowanie 1:1 z poprzednią aplikacją.
export default function Eksport() {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const { toast } = useToast()

  const pobierz = () => {
    if (!start || !end) {
      toast('Podaj początek i koniec zakresu.', 'error')
      return
    }
    window.location.href = `${API}/eksport-csv?start=${start}&end=${end}`
  }

  return (
    <Card className="max-w-2xl p-8">
      <SectionHeader
        title="Generuj raport"
        subtitle="Tabela przestawna (pracownik × dzień) w pliku CSV zgodnym z polskim Excelem."
      />
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <label className="flex flex-col gap-2">
          <span className="field-label">Początek zakresu</span>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="field" />
        </label>
        <label className="flex flex-col gap-2">
          <span className="field-label">Koniec zakresu</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="field" />
        </label>
      </div>
      <Banner variant="info" className="mt-6">
        Plik używa średnika jako separatora i kodowania UTF-8 (BOM), aby polskie znaki poprawnie otwierały się w Excelu.
      </Banner>
      <Button variant="success" size="lg" className="mt-6 w-full" onClick={pobierz}>
        <Icon name="download" className="h-5 w-5" /> Pobierz plik dla Excela (.csv)
      </Button>
    </Card>
  )
}
