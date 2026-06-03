import { useState, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { API } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Import dyspozycji pracowników z pliku CSV. Endpoint zwraca {zapisano, podglad, konflikty}.
export default function Dyspozycje() {
  const fileRef = useRef(null)
  const [fileName, setFileName] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const { toast } = useToast()

  const importuj = async () => {
    const f = fileRef.current
    if (!f?.files.length) {
      toast('Najpierw wybierz plik CSV.', 'error')
      return
    }
    const fd = new FormData()
    fd.append('file', f.files[0])
    setBusy(true)
    setResult(null)
    try {
      const res = await fetch(`${API}/dyspozycje/import-csv`, { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Błąd importu pliku.')
      setResult(data)
      toast(`Zaimportowano. Zapisano ${data.zapisano} nowych wpisów.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <Card className="p-8">
        <SectionHeader
          title="Wgraj dyspozycje pracowników"
          subtitle="Obsługiwany jest format wąski (pracownik, data, dostępność) oraz szeroki (kolumny z datami)."
        />
        <Banner variant="info" className="mb-6">
          Upewnij się, że plik CSV ma poprawne nagłówki. W razie konfliktów (nieznany pracownik) system pokaże je poniżej.
        </Banner>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <label className="group flex flex-1 cursor-pointer items-center gap-3 rounded-xl border border-dashed border-line bg-surface-2 px-4 py-3 text-sm text-muted transition hover:border-mint/50 hover:text-ink">
            <Icon name="upload" className="h-5 w-5" />
            <span className="truncate">{fileName || 'Wybierz plik .csv…'}</span>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => setFileName(e.target.files[0]?.name || '')}
            />
          </label>
          <Button onClick={importuj} disabled={busy} className="whitespace-nowrap">
            {busy ? 'Analiza…' : 'Importuj CSV'}
          </Button>
        </div>
      </Card>

      {result && (
        <Card className="p-8">
          <div className="flex flex-wrap items-center gap-4">
            <div className="rounded-xl border border-success/30 bg-success/10 px-4 py-2 text-sm font-semibold text-success">
              Zapisano nowych: {result.zapisano}
            </div>
            {result.konflikty?.length > 0 && (
              <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-2 text-sm font-semibold text-danger">
                Konflikty: {result.konflikty.length}
              </div>
            )}
          </div>

          {result.konflikty?.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-bold text-danger">Nierozpoznane wiersze</h3>
              <ul className="space-y-1 text-sm text-muted">
                {result.konflikty.map((k, i) => (
                  <li key={i} className="rounded-lg bg-white/[0.03] px-3 py-2">
                    <span className="font-semibold text-ink">{k.wiersz || '—'}</span> — {k.problem}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.podglad?.length > 0 && (
            <div className="mt-6">
              <h3 className="mb-2 text-sm font-bold text-ink">Podgląd ({Math.min(result.podglad.length, 30)} z {result.podglad.length})</h3>
              <div className="overflow-hidden rounded-xl border border-line">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-muted">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Pracownik</th>
                      <th className="px-4 py-3 font-semibold">Data</th>
                      <th className="px-4 py-3 font-semibold">Dostępność</th>
                      <th className="px-4 py-3 font-semibold">Od</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {result.podglad.slice(0, 30).map((p, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="px-4 py-2.5 font-medium text-ink">{p.pracownik}</td>
                        <td className="px-4 py-2.5 text-muted">{ddmmyyyy(p.data)}</td>
                        <td className="px-4 py-2.5">
                          {p.dostepnosc ? (
                            <span className="text-success">Dostępny</span>
                          ) : (
                            <span className="text-danger">Niedostępny</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-muted">{p.od || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
