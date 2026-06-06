import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { WeekSelect } from '../ui/WeekSelect'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'
import { motion } from 'framer-motion'

// Baza imprez z serwera NAS. Lista per tydzień + synchronizacja (skan plików .xlsx).
const pusta = (v) => !v || v === 'None' || v === 'Brak'

export default function Imprezy() {
  const { week } = useData()
  const { toast } = useToast()
  const [imprezy, setImprezy] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const fileInputRef = useRef(null)

  const pobierz = useCallback(async () => {
    const [s, e] = week.split('|')
    setLoading(true)
    try {
      setImprezy(await api(`/imprezy?start=${s}&end=${e}`))
    } catch (err) {
      toast(`Błąd pobierania imprez: ${err.message}`, 'error')
      setImprezy([])
    } finally {
      setLoading(false)
    }
  }, [week, toast])

  useEffect(() => {
    pobierz()
  }, [pobierz])

  // Pozwalamy wskazać CAŁY FOLDER (np. „USTALONE"); atrybuty ustawiamy przez ref.
  useEffect(() => {
    const el = fileInputRef.current
    if (el) {
      el.setAttribute('webkitdirectory', '')
      el.setAttribute('directory', '')
    }
  }, [])

  const wzorPliku = /^(\d{4})\.(\d{2})\.(\d{2})\s*-\s*(.+)\.xlsx$/i

  // Synchronizacja: laptop czyta pliki z wybranego folderu (NAS w Finderze), parsuje je
  // LOKALNIE (SheetJS) i wysyła na serwer tylko pola (data, klient, godzina, sala, osoby).
  const naWyborFolderu = async (e) => {
    const wszystkie = Array.from(e.target.files || [])
    e.target.value = '' // pozwól wybrać ten sam folder ponownie
    const [s, en] = week.split('|')
    const kandydaci = wszystkie.filter((f) => {
      const m = f.name.match(wzorPliku)
      if (!m) return false
      const d = `${m[1]}-${m[2]}-${m[3]}`
      return d >= s && d <= en // tylko pliki z bieżącego tygodnia
    })
    if (kandydaci.length === 0) {
      toast('Brak plików imprez (.xlsx) z tego tygodnia w wybranym folderze.', 'info')
      return
    }

    setSyncing(true)
    try {
      const XLSX = await import('xlsx') // doczytywane na żądanie (osobny chunk)
      const imprezy = []
      let bledyParsowania = 0
      for (const f of kandydaci) {
        const m = f.name.match(wzorPliku)
        try {
          const wb = XLSX.read(new Uint8Array(await f.arrayBuffer()), { type: 'array' })
          const ws = wb.Sheets[wb.SheetNames[0]]
          const v = (addr) => (ws[addr] ? ws[addr].v : undefined)
          // Komórka czasu w Excelu to UŁAMEK DOBY (18:00 = 0.75). Zamieniamy na "HH:MM".
          const godzina = (addr) => {
            const c = ws[addr]
            if (!c || c.v == null) return null
            if (typeof c.v === 'number') {
              const min = (((Math.round((c.v - Math.floor(c.v)) * 1440)) % 1440) + 1440) % 1440
              return `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`
            }
            return String(c.v).trim() // już tekst (np. "18:00")
          }
          imprezy.push({
            data: `${m[1]}-${m[2]}-${m[3]}`,
            klient: m[4].trim(),
            godzina: godzina('J1'), // godzina (ułamek doby → HH:MM)
            sala: v('J2') != null ? String(v('J2')).trim() : null, // sala
            liczba_osob: Number.isFinite(+v('H8')) ? Math.trunc(+v('H8')) : 0, // ilość osób
            nazwa_pliku: f.name,
          })
        } catch {
          bledyParsowania += 1
        }
      }
      const data = await api(`/imprezy/ingest?start=${s}&end=${en}`, 'POST', { imprezy })
      toast(
        `Wysłano ${imprezy.length} imprez — dodano ${data.dodano}, zaktualizowano ${data.zaktualizowano}, błędy ${data.bledy + bledyParsowania}.`,
        'success',
      )
      await pobierz()
    } catch (err) {
      toast(`Błąd synchronizacji: ${err.message}`, 'error')
    } finally {
      setSyncing(false)
    }
  }

  const [s, e] = week.split('|')

  return (
    <Card className="mx-auto max-w-3xl p-6 sm:p-8">
      {/* Wybór tygodnia, na który skanujemy imprezy (zmienia też wspólny tydzień aplikacji). */}
      <div className="mb-5">
        <WeekSelect />
      </div>
      <SectionHeader title="Baza Imprez (Ustalone)" subtitle={`Skan plików .xlsx dla tygodnia ${ddmmyyyy(s)} — ${ddmmyyyy(e)}`}>
        <Button onClick={() => fileInputRef.current?.click()} disabled={syncing}>
          {syncing ? <Spinner className="h-4 w-4" /> : <Icon name="refresh" className="h-4 w-4" />}
          {syncing ? 'Synchronizacja…' : 'Synchronizuj'}
        </Button>
        <input ref={fileInputRef} type="file" multiple accept=".xlsx" className="hidden" onChange={naWyborFolderu} />
      </SectionHeader>

      <Banner variant="info" className="mb-6">
        Podłącz dysk NAS w Finderze, kliknij „Synchronizuj" i wskaż folder z plikami imprez (np. „USTALONE”).
        Pliki z tego tygodnia są odczytywane <strong>na Twoim laptopie</strong> — na serwer leci tylko data,
        klient, godzina, sala i liczba osób (serwer nie czyta NAS-a i nie parsuje Excela).
      </Banner>

      {/* Karty zamiast tabeli — czytelne na mobile, nic się nie ucina. */}
      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : imprezy.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">
          Brak imprez na ten tydzień. Kliknij „Synchronizuj NAS”.
        </div>
      ) : (
        <div className="space-y-3">
          {imprezy.map((imp, i) => (
            <motion.div
              key={imp.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i, 8) * 0.045, duration: 0.4, ease: [0.23, 1, 0.32, 1] } }}
              whileHover={{ y: -4 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="rounded-2xl border border-line bg-white/[0.02] p-4 transition-colors hover:bg-white/[0.04]"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="font-bold text-ink">{imp.klient}</span>
                <span className="shrink-0 font-mono text-xs font-semibold text-muted">{ddmmyyyy(imp.data)}</span>
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
                {!pusta(imp.sala) && (
                  <span className="inline-flex items-center gap-1 rounded-lg border border-mint/20 bg-mint/10 px-2.5 py-1 font-mono font-bold text-mint">
                    <Icon name="pin" className="h-3 w-3" /> {imp.sala}
                  </span>
                )}
                {!pusta(imp.godzina) && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1 font-mono font-semibold text-ink">
                    <Icon name="clock" className="h-3 w-3" /> {imp.godzina}
                  </span>
                )}
                {imp.liczba_osob > 0 && (
                  <span className="inline-flex items-center gap-1 text-muted">
                    <Icon name="users" className="h-3.5 w-3.5" /> <span className="font-bold text-ink">{imp.liczba_osob}</span> os.
                  </span>
                )}
                {pusta(imp.sala) && pusta(imp.godzina) && !(imp.liczba_osob > 0) && (
                  <span className="italic text-muted">Brak szczegółów</span>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </Card>
  )
}
