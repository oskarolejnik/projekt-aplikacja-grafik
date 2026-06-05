import { useState, useEffect, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

// Zarządzanie kontami: tworzenie loginów dla pracowników, role, reset hasła,
// aktywność, usuwanie. Realizuje model „admin provisionuje konta”.
export default function Konta() {
  const { pracownicy, reloadDicts } = useData()
  const { toast, confirm } = useToast()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)

  const [login, setLogin] = useState('')
  const [haslo, setHaslo] = useState('')
  const [rola, setRola] = useState('employee')
  const [pracownikId, setPracownikId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      await reloadDicts()
      setUsers(await api('/users'))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  const utworz = async () => {
    if (!login.trim() || !haslo) {
      toast('Podaj login i hasło.', 'error')
      return
    }
    try {
      await api('/users', 'POST', {
        login: login.trim(),
        haslo,
        rola,
        pracownik_id: pracownikId ? +pracownikId : null,
      })
      setLogin(''); setHaslo(''); setPracownikId(''); setRola('employee')
      toast('Konto utworzone.', 'success')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const provision = async () => {
    if (!(await confirm('Utworzyć konta dla wszystkich pracowników bez konta?', { danger: false, confirmText: 'Utwórz' }))) return
    try {
      const r = await api('/users/provision', 'POST')
      if (!r.utworzone.length) toast('Wszyscy pracownicy mają już konta.', 'info')
      else toast(`Utworzono ${r.utworzone.length}: ${r.utworzone.map((u) => `${u.login}/${u.haslo_tymczasowe}`).join(', ')}`, 'success')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const toggleAktywny = async (u) => {
    try {
      await api(`/users/${u.id}`, 'PUT', { aktywny: !u.aktywny })
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }
  const resetHaslo = async (u) => {
    const nowe = Math.random().toString(36).slice(2, 10)
    try {
      await api(`/users/${u.id}/reset-haslo`, 'POST', { haslo: nowe })
      toast(`Nowe hasło dla „${u.login}”: ${nowe}`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    }
  }
  const usun = async (u) => {
    if (!(await confirm(`Usunąć konto „${u.login}”?`))) return
    try {
      await api(`/users/${u.id}`, 'DELETE')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div className="space-y-8">
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Nowe konto" subtitle="Utwórz login dla pracownika lub administratora.">
          <Button variant="ghost" onClick={provision}>
            <Icon name="users" className="h-4 w-4" /> Konta dla wszystkich
          </Button>
        </SectionHeader>
        <div className="mx-auto max-w-lg">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Login" className="field" autoComplete="off" />
            <input value={haslo} onChange={(e) => setHaslo(e.target.value)} type="text" placeholder="Hasło" className="field" autoComplete="off" />
            <select value={rola} onChange={(e) => setRola(e.target.value)} className="field">
              <option value="employee" className="bg-surface">Pracownik</option>
              <option value="admin" className="bg-surface">Administrator</option>
            </select>
            <select value={pracownikId} onChange={(e) => setPracownikId(e.target.value)} className="field">
              <option value="" className="bg-surface">— Pracownik (opcjonalnie) —</option>
              {pracownicy.map((p) => (
                <option key={p.id} value={p.id} className="bg-surface text-ink">{p.imie} {p.nazwisko}</option>
              ))}
            </select>
          </div>
          <Banner variant="info" className="mt-4">
            Powiąż konto pracownika z osobą z listy — dzięki temu jego zgłoszenia trafią do właściwej dyspozycyjności.
          </Banner>
          <Button className="mt-5 w-full" onClick={utworz}>
            <Icon name="plus" className="h-4 w-4" /> Utwórz konto
          </Button>
        </div>
      </Card>

      {/* Lista kont — karty (czytelne na mobile, nic się nie ucina) */}
      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : users.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted">Brak kont.</Card>
      ) : (
        <div className="space-y-3">
          {users.map((u, i) => (
            <div key={u.id} className="animate-fade-up rounded-2xl border border-line bg-white/[0.02] p-4" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-ink">{u.login}</span>
                    <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${u.rola === 'admin' ? 'bg-lemon/15 text-lemon' : 'bg-mint/15 text-mint'}`}>
                      {u.rola === 'admin' ? 'Administrator' : 'Pracownik'}
                    </span>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-muted">
                    Aktywne
                    <button
                      onClick={() => toggleAktywny(u)}
                      className={`relative h-5 w-9 rounded-full transition-colors ${u.aktywny ? 'bg-success' : 'bg-white/15'}`}
                      aria-label="Przełącz aktywność konta"
                    >
                      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${u.aktywny ? 'left-[18px]' : 'left-0.5'}`} />
                    </button>
                  </label>
                </div>

                <div className="text-xs text-muted">
                  Pracownik: <span className="text-ink">{u.imie ? `${u.imie} ${u.nazwisko}` : '— niepowiązane —'}</span>
                </div>

                <div className="flex justify-end gap-2 border-t border-line pt-3">
                  <Button size="sm" variant="ghost" onClick={() => resetHaslo(u)}>Reset hasła</Button>
                  <Button size="sm" variant="danger" onClick={() => usun(u)} aria-label="Usuń konto">
                    <Icon name="trash" className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
