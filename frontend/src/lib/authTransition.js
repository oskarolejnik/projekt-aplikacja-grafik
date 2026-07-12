import { setToken } from './api'
import { purgeReservationPrivacy } from './reservationPrivacy'

// Każda ścieżka, która ustanawia nową tożsamość, musi najpierw unieważnić
// historię i pamięć PII poprzedniego operatora — również w innych kartach.
export function establishAuthenticatedSession(token, remember) {
  purgeReservationPrivacy({ reason: 'login' })
  if (remember === undefined) setToken(token)
  else setToken(token, remember)
}
