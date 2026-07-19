"""R7.2: anonimowy popyt odrzucony i lejek listy oczekujących.

Moduł utrwala wyłącznie zamknięte kategorie operacyjne. Nie przyjmuje nazwiska,
kontaktu, notatki, identyfikatora użytkownika, sesji, IP ani identyfikatora
waitlisty/rezerwacji. Publiczne odpowiedzi są agregatami bez identyfikatorów.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
import hmac
import secrets
from statistics import median
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import reservation_operational
import reservation_service


REASON_LABELS = {
    "service_closed": "Lokal lub serwis jest zamknięty",
    "channel_unavailable": "Kanał rezerwacji jest niedostępny",
    "booking_window": "Termin jest poza oknem rezerwacji",
    "party_policy": "Grupa nie mieści się w zasadach rezerwacji",
    "pacing_limit": "Limit nowych rezerwacji w przedziale",
    "concurrent_limit": "Limit jednoczesnej obsady",
    "resource_occupied": "Pasujące stoły są już zajęte",
    "no_capacity_match": "Brak konfiguracji stołów dla grupy",
    "operator_decision": "Operator dodał wpis mimo dostępnej rezerwacji",
    "legacy_unknown": "Brak danych historycznych",
    "other": "Inna reguła dostępności",
}
REASON_CODES = frozenset(REASON_LABELS)
RESOURCE_KINDS = frozenset({
    "policy",
    "service_capacity",
    "table_or_combination",
    "capacity",
    "available",
    "unknown",
})
REJECTED_DEMAND_REASON_CODES = REASON_CODES - {
    "operator_decision",
    "legacy_unknown",
}

_CODE_TO_CLASSIFICATION = {
    "DATE_CLOSED": ("service_closed", "policy"),
    "OUTSIDE_SERVICE_WINDOW": ("service_closed", "policy"),
    "CHANNEL_NOT_ALLOWED": ("channel_unavailable", "policy"),
    "ADVANCE_WINDOW_EXCEEDED": ("booking_window", "policy"),
    "BOOKING_CUTOFF_REACHED": ("booking_window", "policy"),
    "DATE_IN_PAST": ("booking_window", "policy"),
    "SLOT_NOT_OFFERED": ("booking_window", "policy"),
    "PARTY_SIZE_ABOVE_MAX": ("party_policy", "policy"),
    "PARTY_SIZE_BELOW_MIN": ("party_policy", "policy"),
    "LARGE_PARTY_APPROVAL_REQUIRED": ("party_policy", "policy"),
    "LARGE_PARTY_PHONE_ONLY": ("party_policy", "policy"),
    "PACING_COVERS_LIMIT": ("pacing_limit", "service_capacity"),
    "PACING_RESERVATION_LIMIT": ("pacing_limit", "service_capacity"),
    "CONCURRENT_COVERS_LIMIT": ("concurrent_limit", "service_capacity"),
    "CONCURRENT_RESERVATION_LIMIT": ("concurrent_limit", "service_capacity"),
    "RESOURCE_OCCUPIED": ("resource_occupied", "table_or_combination"),
    "RESOURCE_COMPONENT_OCCUPIED": (
        "resource_occupied", "table_or_combination",
    ),
    "NO_CAPACITY_MATCH": ("no_capacity_match", "capacity"),
    "NO_TABLE_CANDIDATE": ("no_capacity_match", "capacity"),
}


@dataclass(frozen=True)
class DemandClassification:
    reason_code: str
    resource_kind: str


def _result_codes(result: Any) -> Iterable[str]:
    evaluation = getattr(result, "evaluation", None)
    for violation in getattr(evaluation, "violations", ()) or ():
        code = getattr(violation, "code", None)
        if code:
            yield str(code)
    for reason in getattr(result, "reasons", ()) or ():
        code = getattr(reason, "code", None)
        if code:
            yield str(code)
    code = getattr(result, "code", None)
    if code:
        yield str(code)


def classify_allocation(result: Any) -> DemandClassification:
    """Mapuje wynik R3/R4 do zamkniętej, stabilnej kategorii serwerowej."""
    if (
        getattr(result, "decision", None) == "allow"
        and getattr(result, "selected", None) is not None
    ):
        return DemandClassification("operator_decision", "available")
    for code in _result_codes(result):
        mapped = _CODE_TO_CLASSIFICATION.get(code)
        if mapped is not None:
            return DemandClassification(*mapped)
    return DemandClassification("other", "unknown")


def event_identity(
    *,
    source_kind: str,
    raw_key: str | None,
    payload: Any,
    secret: str,
) -> reservation_service.IdempotencyIdentity:
    if source_kind not in {"availability", "waitlist"}:
        raise ValueError("unsupported demand source")
    return reservation_service.required_idempotency_identity(
        operation=f"demand.{source_kind}",
        raw_key=raw_key,
        payload=payload,
        secret=secret,
    )


def record_event(
    db: Session,
    *,
    source_kind: str,
    channel: str,
    requested_date: date,
    requested_time: time | None,
    party_size: int,
    classification: DemandClassification,
    identity: reservation_service.IdempotencyIdentity,
    captured_at: datetime,
) -> tuple[models.ReservationDemandEvent, bool]:
    """Dodaje anonimowy fakt albo bezpiecznie odtwarza jego idempotentny zapis."""
    if source_kind not in {"availability", "waitlist"}:
        raise ValueError("unsupported demand source")
    if channel not in {"online", "wewnetrzna"}:
        raise ValueError("unsupported demand channel")
    if classification.reason_code not in REASON_CODES:
        raise ValueError("unsupported demand reason")
    if classification.resource_kind not in RESOURCE_KINDS:
        raise ValueError("unsupported demand resource")
    if isinstance(party_size, bool) or not 1 <= int(party_size) <= 500:
        raise ValueError("party_size outside supported range")

    existing = db.query(models.ReservationDemandEvent).filter(
        models.ReservationDemandEvent.source_kind == source_kind,
        models.ReservationDemandEvent.event_key_hash == identity.key_hash,
    ).one_or_none()
    if existing is not None:
        if not hmac.compare_digest(
            existing.request_fingerprint,
            identity.request_fingerprint,
        ):
            raise reservation_service.ReservationError(
                409,
                "DEMAND_IDEMPOTENCY_KEY_REUSED",
                "Ten klucz Idempotency-Key został użyty z innymi danymi.",
                rule="idempotency",
            )
        return existing, True

    event = models.ReservationDemandEvent(
        source_kind=source_kind,
        channel=channel,
        requested_date=requested_date,
        requested_time=requested_time,
        party_size=int(party_size),
        reason_code=classification.reason_code,
        resource_kind=classification.resource_kind,
        event_key_hash=identity.key_hash,
        request_fingerprint=identity.request_fingerprint,
        captured_at=captured_at,
    )
    db.add(event)
    db.flush()
    return event, False


def record_internal_waitlist_event(
    db: Session,
    *,
    requested_date: date,
    requested_time: time | None,
    party_size: int,
    classification: DemandClassification,
    secret: str,
    captured_at: datetime,
) -> models.ReservationDemandEvent:
    safe_payload = {
        "data": requested_date,
        "godz_od": requested_time,
        "liczba_osob": int(party_size),
        "kanal": "wewnetrzna",
    }
    identity = event_identity(
        source_kind="waitlist",
        raw_key=secrets.token_urlsafe(32),
        payload=safe_payload,
        secret=secret,
    )
    event, _ = record_event(
        db,
        source_kind="waitlist",
        channel="wewnetrzna",
        requested_date=requested_date,
        requested_time=requested_time,
        party_size=party_size,
        classification=classification,
        identity=identity,
        captured_at=captured_at,
    )
    return event


def mark_waitlist_attended(db: Session, termin: models.Termin) -> int:
    """Snapshotuje wyłącznie kompletny, poprawny pomiar hosta."""
    measurement = reservation_operational.actual_turn_measurement(termin)
    if (
        termin.status != "odbyla"
        or measurement["pomiar"] != "complete"
        or termin.host_left_at is None
    ):
        return 0
    rows = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.termin_id == termin.id,
        models.ListaOczekujacych.status == "zaakceptowano",
    ).all()
    changed = 0
    for row in rows:
        if row.attended_at is None:
            row.attended_at = termin.host_left_at
            changed += 1
    return changed


def _party_bucket(value: int) -> str:
    if value <= 2:
        return "1-2"
    if value <= 4:
        return "3-4"
    if value <= 6:
        return "5-6"
    return "7+"


def _percentage(numerator: int, denominator: int) -> int | None:
    return round(numerator / denominator * 100) if denominator else None


def _counter_rows(counter: Counter, *, key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "proby": counts[0], "osoby": counts[1]}
        for value, counts in sorted(
            counter.items(), key=lambda item: (-item[1][0], str(item[0])),
        )
    ]


def _is_canonical_rejection(reason_code: str, resource_kind: str) -> bool:
    """Odróżnia realną odmowę od decyzji operatora i danych historycznych."""
    return (
        reason_code in REJECTED_DEMAND_REASON_CODES
        and resource_kind != "available"
    )


def _is_rejected_attempt(event: models.ReservationDemandEvent) -> bool:
    """Publiczna waitlista kontynuuje availability; wewnętrzna jest nową próbą."""
    if not _is_canonical_rejection(event.reason_code, event.resource_kind):
        return False
    return (
        event.source_kind == "availability" and event.channel == "online"
    ) or (
        event.source_kind == "waitlist" and event.channel == "wewnetrzna"
    )


def aggregate_demand(db: Session, *, start: date, end: date) -> dict[str, Any]:
    """Buduje wyłącznie agregaty R7.2; wynik nie zawiera żadnych ID ani hashy."""
    events = db.query(models.ReservationDemandEvent).filter(
        models.ReservationDemandEvent.requested_date >= start,
        models.ReservationDemandEvent.requested_date <= end,
    ).all()
    waitlists = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.data >= start,
        models.ListaOczekujacych.data <= end,
    ).all()

    rejected_events = [event for event in events if _is_rejected_attempt(event)]
    online_availability_rejections = sum(
        1 for event in rejected_events
        if event.source_kind == "availability" and event.channel == "online"
    )
    internal_waitlist_rejections = sum(
        1 for event in rejected_events
        if event.source_kind == "waitlist" and event.channel == "wewnetrzna"
    )
    online_waitlist_rejections = sum(
        1 for event in events
        if event.source_kind == "waitlist"
        and event.channel == "online"
        and _is_canonical_rejection(event.reason_code, event.resource_kind)
    )
    # `z_waitlista` pozostaje podzbiorem zarejestrowanych odmów. Publiczny wpis
    # jest kontynuacją availability i nie może sam stworzyć brakującej próby.
    attempts_with_waitlist = internal_waitlist_rejections + min(
        online_waitlist_rejections,
        online_availability_rejections,
    )

    reason_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    group_counts: Counter = Counter()
    channel_counts: Counter = Counter()
    resource_counts: Counter = Counter()
    total_people = 0
    for event in rejected_events:
        people = max(0, int(event.party_size or 0))
        total_people += people
        hour = (
            f"{event.requested_time.hour:02d}:00"
            if event.requested_time is not None else "bez_godziny"
        )
        for counter, value in (
            (reason_counts, event.reason_code),
            (hour_counts, hour),
            (group_counts, _party_bucket(people)),
            (channel_counts, event.channel),
            (resource_counts, event.resource_kind),
        ):
            attempts, covers = counter.get(value, (0, 0))
            counter[value] = (attempts + 1, covers + people)

    term_ids = {row.termin_id for row in waitlists if row.termin_id is not None}
    reservations = {
        row.id: row
        for row in (
            db.query(models.Termin).filter(models.Termin.id.in_(term_ids)).all()
            if term_ids else []
        )
    }
    offered = accepted = attended = 0
    offer_minutes = []
    historical_unknown = 0
    waitlists_without_event = 0
    for row in waitlists:
        was_accepted = row.zaakceptowano_at is not None or row.status == "zaakceptowano"
        # Legacy-direct tworzył rezerwację bez osobnego etapu oferty. W lejku
        # zaakceptowanie implikuje przejście przez etap zaoferowania.
        was_offered = (
            row.zaoferowano_at is not None
            or row.status == "zaoferowano"
            or was_accepted
        )
        if was_offered:
            offered += 1
        if was_accepted:
            accepted += 1
        if row.demand_reason_code == "legacy_unknown":
            historical_unknown += 1
        # Nowy wpis z liczbą osób zapisuje event w tej samej transakcji.
        # Legacy sentinel i brak liczby osób są więc owner-row dowodem braku
        # zdarzenia; nie kompensujemy ich osieroconym eventem innego wpisu.
        if row.demand_reason_code == "legacy_unknown" or row.liczba_osob is None:
            waitlists_without_event += 1
        if row.zaoferowano_at is not None and row.utworzono_at is not None:
            seconds = (row.zaoferowano_at - row.utworzono_at).total_seconds()
            if seconds >= 0:
                offer_minutes.append(round(seconds / 60))

        if not was_accepted:
            continue
        reservation = reservations.get(row.termin_id)
        if row.attended_at is not None:
            # Pole powstaje wyłącznie po walidacji pomiaru i jest trwałym faktem
            # lifecycle także po późniejszej anonimizacji/usunięciu właściciela.
            complete = True
        elif reservation is not None:
            complete = (
                reservation.status == "odbyla"
                and reservation_operational.actual_turn_measurement(reservation)[
                    "pomiar"
                ] == "complete"
            )
        else:
            complete = False
        if complete:
            attended += 1

    first_tracking = db.query(
        func.min(models.ReservationDemandEvent.captured_at),
    ).scalar()
    days = (end - start).days + 1
    return {
        "okres": {"od": str(start), "do": str(end), "dni": days},
        "odrzucony_popyt": {
            "proby": len(rejected_events),
            "osoby": total_people,
            "z_waitlista": attempts_with_waitlist,
            "przyczyny": [
                {
                    "kod": code,
                    "etykieta": REASON_LABELS.get(code, REASON_LABELS["other"]),
                    "proby": counts[0],
                    "osoby": counts[1],
                }
                for code, counts in sorted(
                    reason_counts.items(),
                    key=lambda item: (-item[1][0], str(item[0])),
                )
            ],
            "wg_godziny": _counter_rows(hour_counts, key="godzina"),
            "wg_wielkosci_grupy": _counter_rows(group_counts, key="grupa"),
            "kanaly": _counter_rows(channel_counts, key="kanal"),
            "wg_zasobu": _counter_rows(resource_counts, key="zasob"),
        },
        "waitlista": {
            "wpisy": len(waitlists),
            "zaoferowano": offered,
            "zaakceptowano": accepted,
            "odbyte": attended,
            "zaoferowano_proc": _percentage(offered, len(waitlists)),
            "zaakceptowano_proc": _percentage(accepted, len(waitlists)),
            "odbyte_proc": _percentage(attended, len(waitlists)),
            "mediana_do_oferty_min": (
                round(float(median(offer_minutes)), 1) if offer_minutes else None
            ),
        },
        "jakosc_danych": {
            "sledzenie_od": (
                first_tracking.date().isoformat() if first_tracking else None
            ),
            "wpisy_bez_zdarzenia": waitlists_without_event,
            "historyczne_bez_przyczyny": historical_unknown,
            "zaakceptowane_bez_potwierdzonej_wizyty": max(
                0, accepted - attended,
            ),
        },
    }
