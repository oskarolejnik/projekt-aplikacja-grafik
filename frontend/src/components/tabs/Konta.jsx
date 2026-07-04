import { useState, useEffect, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

// Zaproszenia do kont: manager wpisuje imię, nazwisko i rolę → dostaje link,
// który wysyła pracownikowi dowolnym kanałem. Pracownik z linku sam ustala
// login i hasło, a konto od razu jest przypięte do właściwej osoby.
// (Publiczna samodzielna rejestracja jest domyślnie wyłączona.)
function Zaproszenia({ pracownicy }) {
  const { toast, confirm } = useToast()
  const [zaproszenia, setZaproszenia] = useState([])
  const [imie, setImie] = useState('')
  const [nazwisko, setNazwisko] = useState('')
  const [rola, setRola] = useState('employee')
  const [pracownikId, setPracownikId] = useState('')
  const [swiezyLink, setSwiezyLink] = useState(null)

  const load = useCallback(async () => {
    try {
      setZaproszenia((await api('/zaproszenia')).zaproszenia)
    } catch (e) {
      toast(e.message, 'error')
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const pelnyLink = (z) => `${window.location.origin}/${z.link.startsWith('/') ? z.link.slice(1) : z.link}`

  const kopiuj = async (z) => {
    try {
      await navigator.clipboard.writeText(pelnyLink(z))
      toast('Link skopiowany — wyślij go pracownikowi.', 'success')
    } catch {
      toast('Nie udało się skopiować — zaznacz link ręcznie.', 'error')
    }
  }

  const zapros = async () => {
    const body = pracownikId
      ? { pracownik_id: +pracownikId, rola }
      : { imie: imie.trim(), nazwisko: nazwisko.trim(), rola }
    if (!pracownikId && (!body.imie || !body.nazwisko)) {
      toast('Podaj imię i nazwisko albo wybierz pracownika z listy.', 'error')
      return
    }
    try {
      const z = await api('/zaproszenia', 'POST', body)
      setSwiezyLink(z)
      setImie(''); setNazwisko(''); setPracownikId(''); setRola('employee')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const uniewaznij = async (z) => {
    if (!(await confirm(`Unieważnić zaproszenie dla „${z.pracownik}”?`))) return
    try {
      await api(`/zaproszenia/${z.id}`, 'DELETE')
      if (swiezyLink?.id === z.id) setSwiezyLink(null)
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const aktywne = zaproszenia.filter((z) => z.status === 'aktywne')

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader
        title="Zaproś pracownika"
        subtitle="Wpisz dane i rolę — wyślij pracownikowi link, z którego sam założy swoje konto."
      />
      <div className="mx-auto max-w-lg">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <input value={imie} onChange={(e) => setImie(e.target.value)} placeholder="Imię" className="field" autoComplete="off" disabled={!!pracownikId} />
          <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} placeholder="Nazwisko" className="field" autoComplete="off" disabled={!!pracownikId} />
          <select value={rola} onChange={(e) => setRola(e.target.value)} className="field">
            <option value="employee" className="bg-surface">Pracownik obsługa</option>
            <option value="kuchnia" className="bg-surface">Pracownik kuchnia</option>
            <option value="szef_kuchni" className="bg-surface">Szef kuchni</option>
            <option value="szef" className="bg-surface">Szef (podgląd)</option>
          </select>
          <select value={pracownikId} onChange={(e) => setPracownikId(e.target.value)} className="field">
            <option value="" className="bg-surface">— albo istniejący pracownik —</option>
            {pracownicy.map((p) => (
              <option key={p.id} value={p.id} className="bg-surface text-ink">{p.imie} {p.nazwisko}</option>
            ))}
          </select>
        </div>
        <Button className="mt-5 w-full" onClick={zapros}>
          <Icon name="key" className="h-4 w-4" /> Generuj link z zaproszeniem
        </Button>

        {swiezyLink && (
          <div className="mt-4 rounded-xl border border-mint/40 bg-mint/10 p-4">
            <div className="text-xs font-semibold text-mint">
              Zaproszenie dla: {swiezyLink.pracownik} · ważne 7 dni
            </div>
            <div className="mt-2 break-all rounded-lg bg-surface-2 px-3 py-2 font-mono text-xs text-ink">
              {pelnyLink(swiezyLink)}
            </div>
            <Button size="sm" className="mt-3" onClick={() => kopiuj(swiezyLink)}>
              Kopiuj link
            </Button>
          </div>
        )}

        {aktywne.length > 0 && (
          <div className="mt-6 space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Aktywne zaproszenia</div>
            {aktywne.map((z) => (
              <div key={z.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.02] px-4 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-ink">{z.pracownik}</div>
                  <div className="text-xs text-muted">rola: {z.rola} · wygasa {new Date(z.wygasa_at).toLocaleDateString('pl-PL')}</div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="ghost" onClick={() => kopiuj(z)}>Kopiuj</Button>
                  <Button size="sm" variant="danger" onClick={() => uniewaznij(z)} aria-label="Unieważnij zaproszenie">
                    <Icon name="trash" className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}

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
  const zmienRole = async (u, rola) => {
    if (rola === u.rola) return
    try {
      await api(`/users/${u.id}`, 'PUT', { rola })
      toast(`Zmieniono rolę konta „${u.login}”.`, 'success')
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
      <Zaproszenia pracownicy={pracownicy.filter((p) => !users.some((u) => u.pracownik_id === p.id))} />

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Nowe konto" subtitle="Ręczne konto (np. administrator) — pracowników wygodniej zapraszać linkiem.">
          <Button variant="ghost" onClick={provision}>
            <Icon name="users" className="h-4 w-4" /> Konta dla wszystkich
          </Button>
        </SectionHeader>
        <div className="mx-auto max-w-lg">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Login" className="field" autoComplete="off" />
            <input value={haslo} onChange={(e) => setHaslo(e.target.value)} type="text" placeholder="Hasło" className="field" autoComplete="off" />
            <select value={rola} onChange={(e) => setRola(e.target.value)} className="field">
              <option value="employee" className="bg-surface">Pracownik obsługa</option>
              <option value="kuchnia" className="bg-surface">Pracownik kuchnia</option>
              <option value="szef_kuchni" className="bg-surface">Szef kuchni</option>
              <option value="szef" className="bg-surface">Szef (podgląd)</option>
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
                    {/* Rola edytowalna — zmiana zapisuje się od razu (PUT /users). */}
                    <select
                      value={u.rola}
                      onChange={(e) => zmienRole(u, e.target.value)}
                      title="Zmień rolę konta"
                      className="cursor-pointer rounded-md border border-line bg-surface-2 px-2 py-1 text-xs font-semibold text-ink outline-none transition hover:border-mint/50"
                    >
                      <option value="employee" className="bg-surface">Pracownik obsługa</option>
                      <option value="kuchnia" className="bg-surface">Pracownik kuchnia</option>
                      <option value="szef_kuchni" className="bg-surface">Szef kuchni</option>
                      <option value="szef" className="bg-surface">Szef (podgląd)</option>
                      <option value="admin" className="bg-surface">Administrator</option>
                    </select>
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
