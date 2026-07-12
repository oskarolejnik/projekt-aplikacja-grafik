import { warsawDateISO } from './date'

const VIEW_TO_PATH = {
  today: 'dzisiaj',
  calendar: 'kalendarz',
  database: 'baza',
  host: 'host',
}

const PATH_TO_VIEW = Object.fromEntries(
  Object.entries(VIEW_TO_PATH).map(([view, path]) => [path, view]),
)

export const RESERVATION_VIEWS = Object.freeze(Object.keys(VIEW_TO_PATH))
export const RESERVATION_STATUSES = Object.freeze([
  'rezerwacja',
  'potwierdzona',
  'odbyla',
  'no_show',
  'odwolana',
])
export const RESERVATION_SORTS = Object.freeze(['data_desc', 'data_asc', 'nazwisko_asc'])

const pad = (value) => String(value).padStart(2, '0')
const calendarDateIso = (value) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`

export function localDateIso(value = new Date()) {
  return warsawDateISO(value)
}

export function isValidDateIso(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return false
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(year, month - 1, day, 12)
  return parsed.getFullYear() === year
    && parsed.getMonth() === month - 1
    && parsed.getDate() === day
}

export function shiftDateIso(value, amount) {
  const safe = isValidDateIso(value) ? value : localDateIso()
  const [year, month, day] = safe.split('-').map(Number)
  const parsed = new Date(year, month - 1, day, 12)
  parsed.setDate(parsed.getDate() + amount)
  return calendarDateIso(parsed)
}

export function startOfWeekIso(value) {
  const safe = isValidDateIso(value) ? value : localDateIso()
  const [year, month, day] = safe.split('-').map(Number)
  const parsed = new Date(year, month - 1, day, 12)
  const mondayOffset = (parsed.getDay() + 6) % 7
  parsed.setDate(parsed.getDate() - mondayOffset)
  return calendarDateIso(parsed)
}

export function isReservationHash(hash = globalThis.location?.hash || '') {
  return hash === '#/rezerwacje'
    || hash.startsWith('#/rezerwacje/')
    || hash.startsWith('#/rezerwacje?')
}

const allowed = (value, values, fallback = '') => values.includes(value) ? value : fallback
const positiveId = (value) => {
  const parsed = Number.parseInt(value, 10)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export function normalizeReservationRoute(value = {}, fallbackDate = localDateIso()) {
  const date = isValidDateIso(value.date) ? value.date : fallbackDate
  const from = isValidDateIso(value.from) ? value.from : shiftDateIso(date, -30)
  const to = isValidDateIso(value.to) ? value.to : shiftDateIso(date, 180)
  const profileReservationId = positiveId(value.profileReservationId)
  return {
    view: allowed(value.view, RESERVATION_VIEWS, 'today'),
    date,
    mode: value.mode === 'day' ? 'day' : 'week',
    status: allowed(value.status, RESERVATION_STATUSES, ''),
    from: from <= to ? from : to,
    to: from <= to ? to : from,
    sort: allowed(value.sort, RESERVATION_SORTS, 'data_desc'),
    offset: Math.max(0, Number.parseInt(value.offset, 10) || 0),
    // Profil gościa jest zawsze rozwiązywany przez opaque ID rezerwacji. Utrzymanie
    // tego samego ID zaznaczenia zapobiega rozjazdowi profilu i karty pod spodem.
    reservationId: profileReservationId || positiveId(value.reservationId),
    profileReservationId,
  }
}

export function readReservationRoute(hash = globalThis.location?.hash || '') {
  if (!isReservationHash(hash)) return null
  const raw = hash.slice(1)
  const [path, query = ''] = raw.split('?')
  const pathView = path.split('/').filter(Boolean)[1]
  const params = new URLSearchParams(query)
  return normalizeReservationRoute({
    view: PATH_TO_VIEW[pathView] || 'today',
    date: params.get('data'),
    mode: params.get('zakres'),
    status: params.get('status'),
    from: params.get('od'),
    to: params.get('do'),
    sort: params.get('sort'),
    offset: params.get('offset'),
    reservationId: params.get('rezerwacja'),
    profileReservationId: params.get('gosc'),
  })
}

export function buildReservationHash(value) {
  const route = normalizeReservationRoute(value)
  const params = new URLSearchParams()

  if (route.view === 'database') {
    params.set('od', route.from)
    params.set('do', route.to)
    if (route.status) params.set('status', route.status)
    if (route.sort !== 'data_desc') params.set('sort', route.sort)
    if (route.offset) params.set('offset', String(route.offset))
  } else {
    params.set('data', route.date)
    if (route.view === 'calendar' && route.mode !== 'week') params.set('zakres', route.mode)
    if (route.view === 'calendar' && route.status) params.set('status', route.status)
  }
  if (route.reservationId) params.set('rezerwacja', String(route.reservationId))
  if (route.profileReservationId) params.set('gosc', String(route.profileReservationId))

  const query = params.toString()
  return `#/rezerwacje/${VIEW_TO_PATH[route.view]}${query ? `?${query}` : ''}`
}

function writeUrl(hash, { replace = false, state = {}, clearReservationState = false } = {}) {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.hash = hash.startsWith('#') ? hash.slice(1) : hash
  const currentState = { ...(window.history.state || {}) }
  if (clearReservationState) {
    delete currentState.lokaloReservationActor
    delete currentState.lokaloReservationOverlay
    delete currentState.lokaloReservationGuestOverlay
    delete currentState.lokaloReservationReturnTo
    delete currentState.lokaloReservationPrivacyEpoch
  }
  const nextState = { ...currentState, ...state }
  window.history[replace ? 'replaceState' : 'pushState'](nextState, '', url)
  window.dispatchEvent(new Event('lokalo:reservation-route'))
}

export function navigateReservationRoute(value, options = {}) {
  writeUrl(buildReservationHash(value), options)
}

export function clearReservationRoute(options = {}) {
  if (typeof window === 'undefined') return
  if (!isReservationHash(window.location.hash)) {
    const currentState = { ...(window.history.state || {}) }
    const reservationStateKeys = [
      'lokaloReservationActor',
      'lokaloReservationOverlay',
      'lokaloReservationGuestOverlay',
      'lokaloReservationReturnTo',
      'lokaloReservationPrivacyEpoch',
    ]
    if (!reservationStateKeys.some((key) => key in currentState)) return
    delete currentState.lokaloReservationActor
    delete currentState.lokaloReservationOverlay
    delete currentState.lokaloReservationGuestOverlay
    delete currentState.lokaloReservationReturnTo
    delete currentState.lokaloReservationPrivacyEpoch
    window.history.replaceState({ ...currentState, ...(options.state || {}) }, '', window.location.href)
    return
  }
  writeUrl('', { ...options, clearReservationState: true })
}

export function subscribeReservationRoute(callback) {
  if (typeof window === 'undefined') return () => {}
  const listener = (event) => callback(readReservationRoute(), event)
  window.addEventListener('popstate', listener)
  window.addEventListener('hashchange', listener)
  window.addEventListener('lokalo:reservation-route', listener)
  return () => {
    window.removeEventListener('popstate', listener)
    window.removeEventListener('hashchange', listener)
    window.removeEventListener('lokalo:reservation-route', listener)
  }
}
