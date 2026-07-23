import { useState, useEffect, useCallback, useId, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'

const PRESET_RECEPCJA_HOST = 'recepcja_host'
const PIN_STATION_PERMISSIONS = new Set([
  'rezerwacje.operacje',
  'rezerwacje.host',
  'rezerwacje.nadpisuj_limity',
  'rezerwacje.dane_kontaktowe',
])

const isExactReceptionOperator = (user) => {
  const permissions = new Set(user.uprawnienia || [])
  return user.rola === 'szef'
    && user.preset === PRESET_RECEPCJA_HOST
    && permissions.size === PIN_STATION_PERMISSIONS.size
    && [...PIN_STATION_PERMISSIONS].every((permission) => permissions.has(permission))
}

const GRUPY_PRAW = [
  {
    label: 'Widoki managera',
    prawa: [
      { key: 'grafik.podglad', label: 'Grafik i stoły', opis: 'Opublikowany grafik oraz bieżący widok sali.' },
      { key: 'raporty.podglad', label: 'Raport godzin', opis: 'Czas pracy bez automatycznego dostępu do kwot.' },
      { key: 'wyplaty.podglad', label: 'Wypłaty', opis: 'Stawki, kwoty i podsumowania finansowe w raporcie.' },
      { key: 'zeszyt.podglad', label: 'Zeszyt kasowy', opis: 'Podgląd zapisów kasowych bez edycji.' },
      { key: 'imprezy.podglad', label: 'Imprezy', opis: 'Kalendarz i operacyjne informacje o imprezach.' },
      { key: 'rezerwacje.podglad', label: 'Rezerwacje — podgląd', opis: 'Bezpieczne podsumowanie bez zarządzania.' },
    ],
  },
  {
    label: 'Rezerwacje i sala',
    prawa: [
      { key: 'rezerwacje.operacje', label: 'Obsługa rezerwacji', opis: 'Dodawanie, edycja, statusy i lista oczekujących.' },
      { key: 'rezerwacje.host', label: 'Widok hosta', opis: 'Kolejka dnia, sadzanie gości i obrót stolików.' },
      { key: 'rezerwacje.nadpisuj_limity', label: 'Przekraczanie limitów', opis: 'Kontynuacja po ostrzeżeniu, gdy operacja przekracza reguły.' },
      { key: 'rezerwacje.sala', label: 'Konfiguracja sali', opis: 'Stoły, strefy i ich dostępność.' },
      { key: 'rezerwacje.reguly', label: 'Reguły rezerwacji', opis: 'Godziny, limity i wyjątki kalendarza.' },
      { key: 'rezerwacje.analityka', label: 'Analityka rezerwacji', opis: 'Obłożenie i podsumowania operacyjne.' },
      { key: 'rezerwacje.eksport', label: 'Eksport danych gości', opis: 'Kontrolowany eksport wyników CRM do pliku CSV.' },
      { key: 'rezerwacje.crm_zarzadzaj', label: 'Porządkowanie CRM', opis: 'Zgody, kontrola jakości i odwracalne scalanie profili.' },
      { key: 'rezerwacje.dane_kontaktowe', label: 'Dane kontaktowe', opis: 'Telefon i adres e-mail gościa.' },
      { key: 'rezerwacje.notatki_wewnetrzne', label: 'Notatki wewnętrzne', opis: 'Treść notatek dopisanych przez zespół.' },
      { key: 'rezerwacje.dane_wrazliwe', label: 'Dane wrażliwe', opis: 'Informacje o alergiach i szczególnych potrzebach.' },
      { key: 'rezerwacje.finanse', label: 'Finanse rezerwacji', opis: 'Podgląd i edycja zadatków.' },
    ],
  },
]

const PRAWA_DOSTEPU = GRUPY_PRAW.flatMap((grupa) => grupa.prawa)

function DostepKonta({ user, pending, onToggle, onReset, onApplyPreset }) {
  const overrides = user.uprawnienia_override || {}
  const liczbaZmian = PRAWA_DOSTEPU.filter(({ key }) => key in overrides).length
  const presetRecepcji = user.preset === PRESET_RECEPCJA_HOST

  return (
    <details className="group rounded-xl border border-line bg-white/[0.02]">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 outline-none focus-visible:ring-2 focus-visible:ring-mint/70 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Icon name="key" className="h-4 w-4 text-muted" />
          Dostęp
        </span>
        <span className="flex items-center gap-2 text-xs text-muted">
          {liczbaZmian > 0 ? `${liczbaZmian} ${liczbaZmian === 1 ? 'zmiana' : 'zmian'}` : 'Ustawienia roli'}
          <Icon name="chevronDown" className="h-4 w-4 transition group-open:rotate-180" />
        </span>
      </summary>

      <div className="space-y-2 border-t border-line p-3">
        <p className="mb-3 text-xs leading-relaxed text-muted">
          Włącz tylko te obszary i dane, których ta osoba potrzebuje w pracy.
        </p>

        <div className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-ink">Recepcja / Host</span>
              {presetRecepcji ? <span className="rounded-full bg-mint/15 px-2 py-0.5 text-xs font-semibold text-mint">Aktywny preset</span> : null}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted">Rezerwacje, widok hosta, kontakty i przekroczenie limitu po ostrzeżeniu — bez finansów i danych wrażliwych.</p>
          </div>
          <Button
            size="sm"
            variant={presetRecepcji ? 'subtle' : 'ghost'}
            disabled={!!pending || presetRecepcji}
            loading={pending === `${user.id}:preset`}
            loadingLabel="Ustawiam…"
            onClick={() => onApplyPreset(user)}
            className="shrink-0"
          >
            {presetRecepcji ? 'Preset aktywny' : 'Zastosuj preset'}
          </Button>
        </div>

        {GRUPY_PRAW.map((grupa) => (
          <div key={grupa.label} className="pt-2">
            <p className="px-2 pb-1 text-xs font-semibold text-muted">{grupa.label}</p>
            {grupa.prawa.map((prawo) => {
              const wlaczone = (user.uprawnienia || []).includes(prawo.key)
              const zapisuje = pending === `${user.id}:${prawo.key}`
              return (
                <button
                  key={prawo.key}
                  type="button"
                  role="switch"
                  aria-checked={wlaczone}
                  disabled={!!pending}
                  onClick={() => onToggle(user, prawo.key, !wlaczone)}
                  className="flex min-h-11 w-full items-center justify-between gap-4 rounded-lg px-2 py-2 text-left transition hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/70 disabled:opacity-60"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-ink">{prawo.label}</span>
                    <span className="block text-xs leading-relaxed text-muted">{prawo.opis}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="hidden text-xs text-muted sm:inline">{zapisuje ? 'Zapisuję…' : wlaczone ? 'Włączone' : 'Wyłączone'}</span>
                    <span className={`relative h-6 w-11 rounded-full transition-colors ${wlaczone ? 'bg-mint' : 'bg-white/15'}`} aria-hidden>
                      <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-transform ${wlaczone ? 'translate-x-6' : 'translate-x-1'}`} />
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        ))}

        <div className="flex justify-end border-t border-line pt-3">
          <Button
            size="sm"
            variant="ghost"
            disabled={!!pending || (liczbaZmian === 0 && !presetRecepcji)}
            onClick={() => onReset(user)}
          >
            Przywróć ustawienia roli
          </Button>
        </div>
      </div>
    </details>
  )
}

function PinStanowiska({ user, onConfiguredChange }) {
  const { confirm } = useToast()
  const inputId = useId()
  const inputRef = useRef(null)
  const configured = Boolean(user.reservation_pin_configured)
  const active = user.aktywny !== false
  const [editing, setEditing] = useState(!configured && active)
  const [pin, setPin] = useState('')
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    if (!active) {
      setPin('')
      setEditing(false)
    } else if (!configured) {
      setEditing(true)
    }
  }, [active, configured])

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const changePin = (event) => {
    setPin(event.target.value.replace(/\D/g, '').slice(0, 6))
    setError('')
    setFeedback('')
  }

  const savePin = async (event) => {
    event.preventDefault()
    if (!active) {
      setError('Aktywuj konto, aby ustawić PIN stanowiska.')
      return
    }
    if (!/^\d{6}$/.test(pin)) {
      setError('PIN musi mieć dokładnie 6 cyfr.')
      inputRef.current?.focus()
      return
    }

    setPending('save')
    setError('')
    setFeedback('')
    try {
      await api(`/users/${user.id}/reservation-pin`, 'PUT', { pin })
      setPin('')
      setEditing(false)
      onConfiguredChange(user.id, true)
      setFeedback(configured ? 'PIN został zmieniony.' : 'PIN został ustawiony.')
    } catch (e) {
      setError(e.message || 'Nie udało się zapisać PIN-u.')
    } finally {
      setPending(null)
    }
  }

  const removePin = async () => {
    const approved = await confirm(
      `Usunąć PIN stanowiska dla konta „${user.login}”? Aktywne sesje tego operatora zostaną zablokowane.`,
      {
        title: 'Usuń PIN stanowiska',
        confirmText: 'Usuń PIN',
        cancelText: 'Zostaw PIN',
        danger: true,
      },
    )
    if (!approved) return

    setPending('remove')
    setError('')
    setFeedback('')
    try {
      await api(`/users/${user.id}/reservation-pin`, 'DELETE')
      setPin('')
      setEditing(true)
      onConfiguredChange(user.id, false)
      setFeedback('PIN został usunięty.')
    } catch (e) {
      setError(e.message || 'Nie udało się usunąć PIN-u.')
    } finally {
      setPending(null)
    }
  }

  const startEditing = () => {
    setPin('')
    setError('')
    setFeedback('')
    setEditing(true)
  }

  const cancelEditing = () => {
    setPin('')
    setError('')
    setEditing(false)
    setFeedback('')
  }

  return (
    <section className="border-t border-line pt-3" aria-labelledby={`${inputId}-title`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`${inputId}-title`} className="text-sm font-semibold text-ink">PIN stanowiska</h3>
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${configured ? 'bg-success/15 text-success' : 'bg-white/[0.06] text-muted'}`}>
              {configured ? 'Ustawiony' : 'Nieustawiony'}
            </span>
          </div>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
            Sześć cyfr do odblokowania wspólnego stanowiska. PIN nie jest później wyświetlany.
          </p>
        </div>

        {configured && !editing ? (
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={startEditing} disabled={!!pending || !active}>
              Zmień PIN
            </Button>
            <Button
              size="sm"
              variant="subtle"
              className="text-danger hover:text-danger"
              onClick={removePin}
              disabled={!!pending}
              loading={pending === 'remove'}
              loadingLabel="Usuwam…"
            >
              Usuń PIN
            </Button>
          </div>
        ) : null}
      </div>

      {!active ? (
        <p className="mt-3 text-sm text-muted">Aktywuj konto, aby ustawić lub zmienić PIN.</p>
      ) : null}

      {editing ? (
        <form onSubmit={savePin} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end" noValidate>
          <label htmlFor={`${inputId}-pin`} className="field-label w-full sm:max-w-xs">
            Nowy PIN stanowiska
            <input
              ref={inputRef}
              id={`${inputId}-pin`}
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="off"
              maxLength={6}
              value={pin}
              onChange={changePin}
              disabled={!!pending}
              aria-invalid={error ? 'true' : undefined}
              aria-describedby={`${inputId}-hint${error ? ` ${inputId}-error` : ''}`}
              className="field mt-1.5 min-h-11 text-center text-lg tracking-[0.3em] disabled:cursor-wait disabled:opacity-60"
            />
            <span id={`${inputId}-hint`} className="mt-1.5 block normal-case tracking-normal text-muted">
              Dokładnie 6 cyfr.
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              size="sm"
              loading={pending === 'save'}
              loadingLabel="Zapisuję…"
              disabled={!!pending}
            >
              {configured ? 'Zapisz nowy PIN' : 'Ustaw PIN'}
            </Button>
            {configured ? (
              <Button type="button" size="sm" variant="subtle" onClick={cancelEditing} disabled={!!pending}>
                Anuluj
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}

      {error ? <p id={`${inputId}-error`} className="mt-3 text-sm text-danger" role="alert">{error}</p> : null}
      {feedback ? <p className="mt-3 text-sm text-success" role="status">{feedback}</p> : null}
    </section>
  )
}

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
  const [permissionPending, setPermissionPending] = useState(null)

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
      const presetUprawnien = rola === PRESET_RECEPCJA_HOST ? PRESET_RECEPCJA_HOST : null
      await api('/users', 'POST', {
        login: login.trim(),
        haslo,
        rola: presetUprawnien ? 'szef' : rola,
        pracownik_id: pracownikId ? +pracownikId : null,
        ...(presetUprawnien ? { preset: presetUprawnien } : {}),
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
  const zapiszDostep = async (u, body, pendingKey) => {
    setPermissionPending(pendingKey)
    try {
      const updated = await api(`/users/${u.id}/uprawnienia`, 'PUT', body)
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setPermissionPending(null)
    }
  }
  const toggleDostep = (u, permission, enabled) => {
    const next = { ...(u.uprawnienia_override || {}), [permission]: enabled }
    return zapiszDostep(u, { uprawnienia_override: next }, `${u.id}:${permission}`)
  }
  const resetDostep = (u) => zapiszDostep(u, { uprawnienia_override: {} }, `${u.id}:reset`)
  const updatePinConfigured = (userId, reservationPinConfigured) => {
    setUsers((current) => current.map((user) => (
      user.id === userId
        ? { ...user, reservation_pin_configured: reservationPinConfigured }
        : user
    )))
  }
  const zastosujPresetRecepcji = async (u) => {
    const approved = await confirm(
      `Zastosować preset Recepcja / Host dla konta „${u.login}”? Zastąpi bieżący zakres dostępu tego konta.`,
      {
        title: 'Zmień zakres dostępu',
        confirmText: 'Zastosuj preset',
        cancelText: 'Zostaw bez zmian',
      },
    )
    if (!approved) return
    return zapiszDostep(
      u,
      { preset: PRESET_RECEPCJA_HOST },
      `${u.id}:preset`,
    )
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
        <SectionHeader title="Nowe konto" subtitle="Ręczne konto (np. administrator) — pracowników wygodniej zapraszać linkiem. Powiąż konto pracownika z osobą z listy, aby jego zgłoszenia trafiały do właściwej dyspozycyjności.">
          <Button variant="ghost" onClick={provision}>
            <Icon name="users" className="h-4 w-4" /> Konta dla wszystkich
          </Button>
        </SectionHeader>
        <div className="mx-auto max-w-lg">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="field-label">Login
              <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="np. recepcja" className="field mt-1.5" autoComplete="off" />
            </label>
            <label className="field-label">Hasło startowe
              <input value={haslo} onChange={(e) => setHaslo(e.target.value)} type="text" className="field mt-1.5" autoComplete="off" />
            </label>
            <label className="field-label">Zakres pracy
              <select value={rola} onChange={(e) => setRola(e.target.value)} className="field mt-1.5">
                <option value="employee" className="bg-surface">Pracownik obsługa</option>
                <option value="kuchnia" className="bg-surface">Pracownik kuchnia</option>
                <option value="szef_kuchni" className="bg-surface">Szef kuchni</option>
                <option value="szef" className="bg-surface">Szef (podgląd)</option>
                <option value={PRESET_RECEPCJA_HOST} className="bg-surface">Recepcja / Host</option>
                <option value="admin" className="bg-surface">Administrator</option>
              </select>
            </label>
            <label className="field-label">Powiązany pracownik
              <select value={pracownikId} onChange={(e) => setPracownikId(e.target.value)} className="field mt-1.5">
                <option value="" className="bg-surface">Niepowiązane</option>
                {pracownicy.map((p) => (
                  <option key={p.id} value={p.id} className="bg-surface text-ink">{p.imie} {p.nazwisko}</option>
                ))}
              </select>
            </label>
          </div>
          {rola === PRESET_RECEPCJA_HOST ? (
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Konto otworzy prosty pulpit rezerwacji i hosta. Nie zobaczy grafiku, finansów, notatek wewnętrznych ani danych wrażliwych.
            </p>
          ) : null}
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
                    {u.preset === PRESET_RECEPCJA_HOST ? (
                      <span className="rounded-full bg-mint/15 px-2 py-1 text-xs font-semibold text-mint">Recepcja / Host</span>
                    ) : null}
                    {/* Rola edytowalna — zmiana zapisuje się od razu (PUT /users). */}
                    <select
                      value={u.rola}
                      onChange={(e) => zmienRole(u, e.target.value)}
                      title="Zmień rolę konta"
                      className="min-h-11 cursor-pointer rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs font-semibold text-ink outline-none transition hover:border-mint/50 focus-visible:ring-2 focus-visible:ring-mint/70"
                    >
                      <option value="employee" className="bg-surface">Pracownik obsługa</option>
                      <option value="kuchnia" className="bg-surface">Pracownik kuchnia</option>
                      <option value="szef_kuchni" className="bg-surface">Szef kuchni</option>
                      <option value="szef" className="bg-surface">
                        {u.preset === PRESET_RECEPCJA_HOST ? 'Recepcja / Host' : 'Szef (podgląd)'}
                      </option>
                      <option value="admin" className="bg-surface">Administrator</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted">
                    <span>Aktywne</span>
                    <button
                      type="button"
                      onClick={() => toggleAktywny(u)}
                      role="switch"
                      aria-checked={u.aktywny}
                      className="flex h-11 w-11 items-center justify-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/70"
                      aria-label="Przełącz aktywność konta"
                    >
                      <span className={`relative h-5 w-9 rounded-full transition-colors ${u.aktywny ? 'bg-success' : 'bg-white/15'}`} aria-hidden>
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${u.aktywny ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
                      </span>
                    </button>
                  </div>
                </div>

                <div className="text-xs text-muted">
                  Pracownik: <span className="text-ink">{u.imie ? `${u.imie} ${u.nazwisko}` : '— niepowiązane —'}</span>
                </div>

                {isExactReceptionOperator(u) ? (
                  <PinStanowiska user={u} onConfiguredChange={updatePinConfigured} />
                ) : null}

                {u.rola === 'szef' && (
                  <DostepKonta
                    user={u}
                    pending={permissionPending}
                    onToggle={toggleDostep}
                    onReset={resetDostep}
                    onApplyPreset={zastosujPresetRecepcji}
                  />
                )}

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
