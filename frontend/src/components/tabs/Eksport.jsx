import { useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { API, pobierzPlik } from '../../lib/api'
import { useToast } from '../ui/Toast'

const MIESIACE = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień']

// Eksport danych: grafik (CSV pracownik × dzień) + wypłaty miesięczne (Excel .xlsx dla księgowej).
export default function Eksport() {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const teraz = new Date()
  const [rok, setRok] = useState(teraz.getFullYear())
  const [miesiac, setMiesiac] = useState(teraz.getMonth() + 1)
  const [busy, setBusy] = useState(false)
  const { toast } = useToast()

  const pobierzCsv = () => {
    if (!start || !end) { toast('Podaj początek i koniec zakresu.', 'error'); return }
    window.location.href = `${API}/eksport-csv?start=${start}&end=${end}`
  }

  const pobierzWyplaty = async () => {
    setBusy(true)
    try {
      await pobierzPlik(`/eksport/wyplaty?rok=${rok}&miesiac=${miesiac}`,
        `wyplaty_${rok}_${String(miesiac).padStart(2, '0')}.xlsx`)
      toast('Pobrano raport wypłat.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Wypłaty miesięczne → Excel */}
      <Card className="p-8">
        <SectionHeader title="Wypłaty do Excela"
          subtitle="Miesięczny raport płac (godziny × stawka per stanowisko, wiersze RAZEM) jako gotowy .xlsx dla księgowej. Plik ma formatowanie (nagłówki, sumy); dostęp do danych płacowych jest zapisywany w dzienniku audytu (RODO)." />
        <div className="mt-2 grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-2">
            <span className="field-label">Miesiąc</span>
            <select value={miesiac} onChange={(e) => setMiesiac(Number(e.target.value))} className="field">
              {MIESIACE.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-2">
            <span className="field-label">Rok</span>
            <input type="number" min="2000" max="2100" value={rok} onChange={(e) => setRok(Number(e.target.value))} className="field" />
          </label>
        </div>
        <Button variant="success" size="lg" className="mt-6 w-full" onClick={pobierzWyplaty} disabled={busy}>
          <Icon name="download" className="h-5 w-5" /> {busy ? 'Generuję…' : 'Pobierz wypłaty (.xlsx)'}
        </Button>
      </Card>

      {/* Grafik → CSV */}
      <Card className="p-8">
        <SectionHeader title="Grafik do CSV"
          subtitle="Tabela przestawna (pracownik × dzień) w pliku CSV zgodnym z polskim Excelem. Separator średnik + kodowanie UTF-8 (BOM), aby polskie znaki poprawnie się otwierały." />
        <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-2">
            <span className="field-label">Początek zakresu</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="field" />
          </label>
          <label className="flex flex-col gap-2">
            <span className="field-label">Koniec zakresu</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="field" />
          </label>
        </div>
        <Button variant="success" size="lg" className="mt-6 w-full" onClick={pobierzCsv}>
          <Icon name="download" className="h-5 w-5" /> Pobierz grafik (.csv)
        </Button>
      </Card>
    </div>
  )
}
