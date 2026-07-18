import { reservationActorKey, reservationHistoryState } from './reservationSession'

const PREFIX = 'lokalo:reservations:v1:host-snapshot:'
const CACHE_VERSION = 1
const SNAPSHOT_SCHEMA_VERSION = 1
const PRIVACY_EPOCH_KEY = 'lokaloReservationPrivacyEpoch'
export const HOST_SNAPSHOT_CACHE_TTL_MS = 12 * 60 * 60 * 1000

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const CLOCK_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/
const RESERVATION_STATUSES = new Set(['rezerwacja', 'potwierdzona', 'odwolana', 'odbyla', 'no_show'])
const HOST_PHASES = new Set(['przybyl', 'posadzony', 'rachunek', 'oplacony', 'wyszedl'])
const WAITLIST_STATUSES = new Set(['oczekuje', 'zaoferowano', 'zaakceptowano', 'wygasla', 'anulowano', 'odwolany'])
const TABLE_STATUSES = new Set([
  'nieaktywny',
  'potwierdzony',
  'zarezerwowany',
  'wstrzymany',
  'zajety_live',
  'bez_rezerwacji',
])

const storageForSession = () => {
  try {
    return globalThis.sessionStorage || null
  } catch {
    return null
  }
}

const isRecord = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const isIsoDay = (value) => {
  if (typeof value !== 'string' || !DAY_PATTERN.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

const safeTimestamp = (value) => (
  typeof value === 'string' && value.length <= 64 && Number.isFinite(Date.parse(value))
    ? value
    : null
)

const safeClock = (value) => (typeof value === 'string' && CLOCK_PATTERN.test(value) ? value : null)
const safeBoolean = (value) => (typeof value === 'boolean' ? value : null)
const safeInteger = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => (
  Number.isInteger(value) && value >= min && value <= max ? value : null
)
const safeNumber = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => (
  Number.isFinite(value) && value >= min && value <= max ? value : null
)
const safeLabel = (value, maxLength = 96) => {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed ? trimmed.slice(0, maxLength) : null
}
const safeEnum = (value, allowed) => (allowed.has(value) ? value : null)
const safeIds = (value, limit = 16) => (
  Array.isArray(value)
    ? [...new Set(value.map((item) => safeInteger(item)).filter((item) => item !== null))].slice(0, limit)
    : []
)
const safeArray = (value, sanitizer, limit = 2000) => (
  Array.isArray(value) ? value.slice(0, limit).map(sanitizer).filter(Boolean) : []
)

const safeReservation = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    data: isIsoDay(value.data) ? value.data : null,
    godz_od: safeClock(value.godz_od),
    godz_do: safeClock(value.godz_do),
    liczba_osob: safeInteger(value.liczba_osob, 0, 10000),
    stolik_id: safeInteger(value.stolik_id),
    stoliki_dodatkowe: safeIds(value.stoliki_dodatkowe),
    status: safeEnum(value.status, RESERVATION_STATUSES),
    faza_hosta: safeEnum(value.faza_hosta, HOST_PHASES),
    minuty_od_posadzenia: safeInteger(value.minuty_od_posadzenia, 0, 100000),
    nazwisko: 'Gość',
    gosc: null,
  }
}

const safeWaitlistEntry = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    godz_od: safeClock(value.godz_od),
    liczba_osob: safeInteger(value.liczba_osob, 0, 10000),
    status: safeEnum(value.status, WAITLIST_STATUSES),
    nazwisko: 'Gość',
    gosc: null,
  }
}

const safeQueue = (value, day) => {
  const source = isRecord(value) ? value : {}
  const nadchodzace = safeArray(source.nadchodzace, safeReservation)
  const naSali = safeArray(source.na_sali, safeReservation)
  const zakonczone = safeArray(source.zakonczone, safeReservation)
  const waitlista = safeArray(source.waitlista, safeWaitlistEntry)
  return {
    data: day,
    nadchodzace,
    na_sali: naSali,
    zakonczone,
    waitlista,
    podsumowanie: {
      nadchodzace: nadchodzace.length,
      na_sali: naSali.length,
      zakonczone: zakonczone.length,
      waitlista: waitlista.length,
      coverow_na_sali: naSali.reduce((sum, item) => sum + (item.liczba_osob || 0), 0),
    },
  }
}

const safeTimelineTable = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    nazwa: safeLabel(value.nazwa, 48),
    sekcja: safeLabel(value.sekcja, 64),
    strefa: safeLabel(value.strefa, 64),
  }
}

const safeTimelineOccupancy = (value) => {
  if (!isRecord(value)) return null
  const stolikId = safeInteger(value.stolik_id)
  const reservationId = safeInteger(value.rezerwacja_id)
  if (stolikId === null || reservationId === null) return null
  return {
    stolik_id: stolikId,
    godz_od: safeClock(value.godz_od),
    godz_do: safeClock(value.godz_do),
    rezerwacja_id: reservationId,
    liczba_osob: safeInteger(value.liczba_osob, 0, 10000),
    faza_hosta: safeEnum(value.faza_hosta, HOST_PHASES),
    nazwisko: 'Gość',
    gosc: null,
  }
}

const safeTimeline = (value, day) => {
  const source = isRecord(value) ? value : {}
  return {
    data: day,
    stoly: safeArray(source.stoly, safeTimelineTable, 1000),
    godziny: Array.isArray(source.godziny)
      ? source.godziny.slice(0, 288).map(safeClock).filter(Boolean)
      : [],
    zajetosci: safeArray(source.zajetosci, safeTimelineOccupancy),
  }
}

const safeRoom = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    nazwa: safeLabel(value.nazwa, 64),
    aktywna: safeBoolean(value.aktywna),
    kolejnosc: safeInteger(value.kolejnosc, 0, 100000),
  }
}

const safeLiveState = (value) => {
  if (!isRecord(value)) return null
  return {
    otwarte: safeInteger(value.otwarte, 0, 100000),
    zajete: safeBoolean(value.zajete),
    aktualizacja: safeTimestamp(value.aktualizacja),
  }
}

// Rezerwacja przypisana do stolika pozostaje użyteczna offline, ale nie zawiera
// żadnego pola opisującego lub identyfikującego gościa.
const safePlanReservation = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    data: isIsoDay(value.data) ? value.data : null,
    godz_od: safeClock(value.godz_od),
    godz_do: safeClock(value.godz_do),
    liczba_osob: safeInteger(value.liczba_osob, 0, 10000),
    status: safeEnum(value.status, RESERVATION_STATUSES),
    faza_hosta: safeEnum(value.faza_hosta, HOST_PHASES),
  }
}

const safePlanTable = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    nazwa: safeLabel(value.nazwa, 48),
    sala_id: safeInteger(value.sala_id),
    strefa: safeLabel(value.strefa, 64),
    sekcja: safeLabel(value.sekcja, 64),
    kolejnosc: safeInteger(value.kolejnosc, 0, 100000),
    pojemnosc: safeInteger(value.pojemnosc, 0, 10000),
    pojemnosc_min: safeInteger(value.pojemnosc_min, 0, 10000),
    ksztalt: safeLabel(value.ksztalt, 24),
    aktywny: safeBoolean(value.aktywny),
    aktywny_w_planie: safeBoolean(value.aktywny_w_planie),
    plan_x: safeNumber(value.plan_x, 0, 100),
    plan_y: safeNumber(value.plan_y, 0, 100),
    szerokosc: safeNumber(value.szerokosc, 0, 100),
    wysokosc: safeNumber(value.wysokosc, 0, 100),
    obrot: safeNumber(value.obrot, 0, 359),
    rewir_nr: safeInteger(value.rewir_nr, 0, 100000),
    status: safeEnum(value.status, TABLE_STATUSES),
    live: safeLiveState(value.live),
    rezerwacje: safeArray(value.rezerwacje, safePlanReservation, 100),
  }
}

const safeCombination = (value) => {
  if (!isRecord(value)) return null
  const id = safeInteger(value.id)
  if (id === null) return null
  return {
    id,
    nazwa: safeLabel(value.nazwa, 64),
    stoliki: safeIds(value.stoliki, 32),
    pojemnosc_min: safeInteger(value.pojemnosc_min, 0, 10000),
    pojemnosc_max: safeInteger(value.pojemnosc_max, 0, 10000),
    priorytet: safeInteger(value.priorytet, 0, 100000),
    kanal: ['oba', 'online', 'wewnetrzny'].includes(value.kanal) ? value.kanal : null,
  }
}

const safeFloorPlan = (value, day) => {
  const source = isRecord(value) ? value : {}
  const stoliki = safeArray(source.stoliki, safePlanTable, 1000)
  return {
    data: day,
    sala_id: safeInteger(source.sala_id),
    sale: safeArray(source.sale, safeRoom, 200),
    strefy: Array.isArray(source.strefy)
      ? [...new Set(source.strefy.slice(0, 200).map((item) => safeLabel(item, 64)).filter(Boolean))]
      : [],
    stoliki,
    kombinacje: safeArray(source.kombinacje, safeCombination, 1000),
    podsumowanie: {
      bez_rezerwacji: stoliki.filter((item) => item.status === 'bez_rezerwacji').length,
      zarezerwowane: stoliki.filter((item) => ['zarezerwowany', 'potwierdzony'].includes(item.status)).length,
      wstrzymane: stoliki.filter((item) => item.status === 'wstrzymany').length,
      nieaktywne: stoliki.filter((item) => item.status === 'nieaktywny').length,
      zajete_live: stoliki.filter((item) => item.live?.zajete === true).length,
    },
  }
}

const sanitizeSnapshot = (snapshot) => {
  if (!isRecord(snapshot) || snapshot.schema_version !== SNAPSHOT_SCHEMA_VERSION || !isIsoDay(snapshot.data)) {
    return null
  }
  const generatedAt = safeTimestamp(snapshot.generated_at)
  const version = safeTimestamp(snapshot.version)
  if (!generatedAt || !version) return null
  return {
    version,
    schema_version: SNAPSHOT_SCHEMA_VERSION,
    data: snapshot.data,
    generated_at: generatedAt,
    kolejka: safeQueue(snapshot.kolejka, snapshot.data),
    os_czasu: safeTimeline(snapshot.os_czasu, snapshot.data),
    plan_sali: safeFloorPlan(snapshot.plan_sali, snapshot.data),
  }
}

const cacheContext = (user) => {
  try {
    const actor = reservationActorKey(user)
    const privacyEpoch = reservationHistoryState(user)[PRIVACY_EPOCH_KEY]
    if (!actor || typeof privacyEpoch !== 'string' || !privacyEpoch) return null
    return { key: `${PREFIX}${actor}`, privacyEpoch }
  } catch {
    return null
  }
}

const removeCacheEntry = (storage, key) => {
  try {
    storage?.removeItem(key)
  } catch {
    // Brak dostępu do storage nie może blokować stanowiska hosta.
  }
}

export function writeHostSnapshotCache(user, snapshot) {
  const context = cacheContext(user)
  const storage = storageForSession()
  if (!context || !storage) return false
  const safeSnapshot = sanitizeSnapshot(snapshot)
  if (!safeSnapshot) {
    removeCacheEntry(storage, context.key)
    return false
  }
  try {
    storage.setItem(context.key, JSON.stringify({
      cacheVersion: CACHE_VERSION,
      privacyEpoch: context.privacyEpoch,
      date: safeSnapshot.data,
      cachedAt: Date.now(),
      snapshot: safeSnapshot,
    }))
    return true
  } catch {
    return false
  }
}

export function readHostSnapshotCache(user, date) {
  const context = cacheContext(user)
  const storage = storageForSession()
  if (!context || !storage) return null
  if (!isIsoDay(date)) {
    removeCacheEntry(storage, context.key)
    return null
  }
  try {
    const saved = JSON.parse(storage.getItem(context.key) || 'null')
    const age = Date.now() - saved?.cachedAt
    const invalid = !isRecord(saved)
      || saved.cacheVersion !== CACHE_VERSION
      || saved.privacyEpoch !== context.privacyEpoch
      || !isIsoDay(saved.date)
      || !Number.isFinite(saved.cachedAt)
      || age < 0
      || age > HOST_SNAPSHOT_CACHE_TTL_MS
    if (invalid) {
      removeCacheEntry(storage, context.key)
      return null
    }
    // Cache celowo przechowuje jeden ostatni dzień. Odczyt innej daty nie może
    // niszczyć poprawnego awaryjnego podglądu, do którego operator może wrócić.
    if (saved.date !== date) return null
    const snapshot = sanitizeSnapshot(saved.snapshot)
    if (!snapshot || snapshot.data !== date || JSON.stringify(snapshot) !== JSON.stringify(saved.snapshot)) {
      removeCacheEntry(storage, context.key)
      return null
    }
    return snapshot
  } catch {
    removeCacheEntry(storage, context.key)
    return null
  }
}

export function clearHostSnapshotCache(user) {
  const context = cacheContext(user)
  const storage = storageForSession()
  if (context && storage) removeCacheEntry(storage, context.key)
}
