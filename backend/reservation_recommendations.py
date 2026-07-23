"""R7.4: evidence-based, explicitly approved reservation recommendations.

The module owns no transaction boundary.  ``simulate`` and ``decide`` flush
their durable rows, but the HTTP router must commit on success and roll back on
any exception.  Recommendation payloads, simulations and audit entries contain
aggregates only; no guest PII is copied into the review ledger.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re
import secrets
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import models
import reservation_operational
import reservation_rules
from deps import utcnow_naive


MIN_COMPLETE_MEASUREMENTS = 20
MIN_COMPLETENESS_PERCENT = 70
MIN_SERVICE_DAYS = 4
MIN_DELTA_MINUTES = 15
PERCENTILE = 75
ROUNDING_MINUTES = 15
SIMULATION_DAYS = 28
MAX_RANGE_DAYS = 366

_SEGMENTS = ("1-2", "3-4", "5+")
_SEGMENT_UPPER_BOUNDS = (2, 4, 999)
_SEGMENT_PARTY_SIZE = {"1-2": 2, "3-4": 4, "5+": 5}
_SEGMENT_INDEX = {name: index for index, name in enumerate(_SEGMENTS)}
_ACCEPT_REASON = "confirmed_after_simulation"
_REJECT_REASONS = frozenset({
    "keep_current_policy",
    "seasonal_sample",
    "operational_decision",
})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WARSAW = ZoneInfo("Europe/Warsaw")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


def _conflict(code: str, message: str) -> HTTPException:
    return _error(409, code, message)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _validate_range(start: date, end: date) -> None:
    if (
        not isinstance(start, date)
        or isinstance(start, datetime)
        or not isinstance(end, date)
        or isinstance(end, datetime)
    ):
        raise _error(
            400,
            "INVALID_RECOMMENDATION_RANGE",
            "Zakres rekomendacji wymaga poprawnych dat.",
        )
    if end < start:
        raise _error(
            400,
            "INVALID_RECOMMENDATION_RANGE",
            "Zakres dat jest odwrócony.",
        )
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise _error(
            400,
            "INVALID_RECOMMENDATION_RANGE",
            f"Zakres może obejmować maksymalnie {MAX_RANGE_DAYS} dni.",
        )


def _segment(people: Any) -> str | None:
    if isinstance(people, bool) or not isinstance(people, int) or people <= 0:
        return None
    if people <= 2:
        return "1-2"
    if people <= 4:
        return "3-4"
    return "5+"


def _positive_minutes(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= 1439 else None


def _threshold_config(
    service: models.GodzinyOtwarcia,
) -> dict[str, Any] | None:
    """Return the only configuration shapes R7.4 is allowed to mutate."""
    raw = service.turn_time_progi
    if raw is None:
        values = [
            reservation_rules.turn_time(service, party_size)
            for party_size in (2, 4, 5)
        ]
        if any(_positive_minutes(value) is None for value in values):
            return None
        return {"mode": "default", "values": values}

    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    values: list[int] = []
    for item, expected_upper in zip(raw, _SEGMENT_UPPER_BOUNDS):
        if not isinstance(item, Mapping) or item.get("do_osob") != expected_upper:
            return None
        minutes = _positive_minutes(item.get("min"))
        if minutes is None:
            return None
        values.append(minutes)
    return {"mode": "canonical", "values": values}


def _updated_thresholds(
    service: models.GodzinyOtwarcia,
    segment: str,
    proposed_minutes: int,
) -> list[dict[str, int]]:
    config = _threshold_config(service)
    if config is None or segment not in _SEGMENT_INDEX:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Konfiguracja serwisu zmieniła się. Odśwież rekomendacje.",
        )
    if _positive_minutes(proposed_minutes) is None:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Proponowany czas wizyty nie jest już poprawny.",
        )
    values = list(config["values"])
    values[_SEGMENT_INDEX[segment]] = proposed_minutes
    return [
        {"do_osob": upper, "min": minutes}
        for upper, minutes in zip(_SEGMENT_UPPER_BOUNDS, values)
    ]


def _nearest_rank_percentile(values: list[int], percentile: int) -> int:
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100) * len(ordered)))
    return ordered[rank - 1]


def _ceil_to_step(value: int, step: int) -> int:
    return int(math.ceil(value / step) * step)


def _review_state(review: models.ReservationRecommendationReview | None) -> str:
    if review is None:
        return "pending"
    return review.status


def _decision_out(
    review: models.ReservationRecommendationReview,
    *,
    replay: bool = False,
) -> dict[str, Any]:
    return {
        "hash": review.recommendation_hash,
        "recommendation_hash": review.recommendation_hash,
        "simulation_hash": review.simulation_hash,
        "serwis_id": review.service_id,
        "segment": review.segment,
        "stan": review.status,
        "decyzja": review.status if review.status in {"accepted", "rejected"} else None,
        "powod": review.decision_reason,
        "decided_at": (
            review.decided_at.isoformat() if review.decided_at is not None else None
        ),
        "replay": replay,
    }


def _recommendation_candidates(db, start: date, end: date) -> list[dict[str, Any]]:
    reservations = (
        db.query(models.Termin)
        .filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.status == "odbyla",
            models.Termin.data >= start,
            models.Termin.data <= end,
            models.Termin.godz_od.isnot(None),
        )
        .order_by(models.Termin.data, models.Termin.godz_od, models.Termin.id)
        .all()
    )

    evidence: dict[tuple[int, str], dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "complete": [],
            "days": set(),
            "facts": [],
        },
    )
    service_names: dict[int, str | None] = {}

    for reservation in reservations:
        segment = _segment(reservation.liczba_osob)
        if segment is None:
            continue
        service = reservation_rules.serwis_dla_godziny(
            db,
            reservation.data,
            reservation.godz_od,
            strict=True,
        )
        if (
            service is None
            or service.id is None
            or (service.source or {}).get("type") == "exception"
        ):
            continue

        key = (int(service.id), segment)
        group = evidence[key]
        group["total"] += 1
        service_names[int(service.id)] = service.name
        measurement = reservation_operational.actual_turn_measurement(reservation)
        state = measurement["pomiar"]
        minutes = measurement["rzeczywisty_czas_min"]
        group["facts"].append((str(reservation.data), state, minutes))
        if state == "complete":
            group["complete"].append(int(minutes))
            group["days"].add(reservation.data)

    candidates: list[dict[str, Any]] = []
    service_sort: dict[int, tuple[Any, ...]] = {}
    for (service_id, segment), group in evidence.items():
        complete = len(group["complete"])
        total = int(group["total"])
        days = len(group["days"])
        if complete < MIN_COMPLETE_MEASUREMENTS:
            continue
        if complete * 100 < MIN_COMPLETENESS_PERCENT * total:
            continue
        if days < MIN_SERVICE_DAYS:
            continue

        service_row = db.get(models.GodzinyOtwarcia, service_id)
        if service_row is None or not service_row.aktywny:
            continue
        config = _threshold_config(service_row)
        if config is None:
            continue
        current = int(config["values"][_SEGMENT_INDEX[segment]])
        p75 = _nearest_rank_percentile(group["complete"], PERCENTILE)
        proposed = _ceil_to_step(p75, ROUNDING_MINUTES)
        if _positive_minutes(proposed) is None:
            continue
        delta = proposed - current
        if abs(delta) < MIN_DELTA_MINUTES:
            continue

        evidence_hash = _hash({
            "service_id": service_id,
            "segment": segment,
            "facts": sorted(group["facts"]),
        })
        identity = {
            "contract": "reservation-turn-time-recommendation:v1",
            "service_id": service_id,
            "segment": segment,
            "period_start": str(start),
            "period_end": str(end),
            "sample_complete": complete,
            "sample_total": total,
            "service_days": days,
            "p75_minutes": p75,
            "current_minutes": current,
            "proposed_minutes": proposed,
            "configuration_mode": config["mode"],
            "evidence_hash": evidence_hash,
        }
        recommendation_hash = _hash(identity)
        candidates.append({
            "hash": recommendation_hash,
            "recommendation_hash": recommendation_hash,
            "rodzaj": "turn_time",
            "serwis": {
                "id": service_id,
                "nazwa": service_row.nazwa or service_names.get(service_id),
            },
            "segment": segment,
            "proba": complete,
            "zakonczone_wizyty": total,
            "kompletnosc_proc": round(complete / total * 100),
            "dni_serwisu": days,
            "p75_min": p75,
            "obecnie_min": current,
            "proponowane_min": proposed,
            "roznica_min": delta,
            "evidence_hash": evidence_hash,
            "stan": "pending",
        })
        service_sort[service_id] = (
            service_row.dzien_tygodnia,
            service_row.godz_od,
            service_row.id,
        )

    candidates.sort(
        key=lambda item: (
            service_sort[item["serwis"]["id"]],
            _SEGMENT_INDEX[item["segment"]],
        ),
    )
    return candidates


def list_recommendations(db, start: date, end: date) -> dict[str, Any]:
    """Return current, deterministic candidates and durable decision states."""
    _validate_range(start, end)
    candidates = _recommendation_candidates(db, start, end)
    hashes = [candidate["hash"] for candidate in candidates]
    reviews: dict[str, models.ReservationRecommendationReview] = {}
    if hashes:
        reviews = {
            row.recommendation_hash: row
            for row in (
                db.query(models.ReservationRecommendationReview)
                .filter(
                    models.ReservationRecommendationReview.recommendation_hash.in_(
                        hashes,
                    ),
                )
                .all()
            )
        }
    for candidate in candidates:
        candidate["stan"] = _review_state(reviews.get(candidate["hash"]))

    return {
        "start": str(start),
        "end": str(end),
        "progi": {
            "minimalna_proba": MIN_COMPLETE_MEASUREMENTS,
            "minimalna_kompletnosc_proc": MIN_COMPLETENESS_PERCENT,
            "minimalne_dni_serwisu": MIN_SERVICE_DAYS,
            "minimalna_roznica_min": MIN_DELTA_MINUTES,
            "percentyl": PERCENTILE,
            "zaokraglenie_min": ROUNDING_MINUTES,
        },
        "rekomendacje": candidates,
        "decyzje": [
            _decision_out(reviews[candidate["hash"]])
            for candidate in candidates
            if candidate["hash"] in reviews
        ],
    }


def _candidate_or_stale(
    db,
    recommendation_hash: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    if not _valid_hash(recommendation_hash):
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Rekomendacja jest nieaktualna. Odśwież dane.",
        )
    result = list_recommendations(db, start, end)
    candidate = next(
        (
            item
            for item in result["rekomendacje"]
            if secrets.compare_digest(item["hash"], recommendation_hash)
        ),
        None,
    )
    if candidate is None:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Dowody lub konfiguracja zmieniły się. Odśwież rekomendacje.",
        )
    return candidate


def _today_warsaw() -> date:
    return datetime.now(_WARSAW).date()


def _future_service_slots(db, service_id: int) -> tuple[date, date, list[tuple[date, Any]]]:
    horizon_start = _today_warsaw()
    horizon_end = horizon_start + timedelta(days=SIMULATION_DAYS - 1)
    slots: list[tuple[date, Any]] = []
    current = horizon_start
    while current <= horizon_end:
        for start_time, service in reservation_rules.sloty_dnia(db, current):
            if (
                service.id == service_id
                and (service.source or {}).get("type") != "exception"
            ):
                slots.append((current, start_time))
        current += timedelta(days=1)
    return horizon_start, horizon_end, slots


def _availability_snapshot(
    evaluator,
    db,
    slots: list[tuple[date, Any]],
    party_size: int,
) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    available = 0
    for booking_date, start_time in slots:
        result = evaluator(
            db,
            data=booking_date,
            godz_od=start_time,
            osoby=party_size,
            kanal="wewnetrzna",
            intent="simulate",
            alternative_limit=0,
        )
        decision = str(getattr(result, "decision", "unknown") or "unknown")
        decisions[decision] += 1
        is_available = getattr(result, "available", None)
        if is_available is None:
            is_available = (
                decision == "allow"
                and getattr(result, "selected", None) is not None
            )
        if bool(is_available):
            available += 1
    return {
        "available": available,
        "decisions": {
            key: decisions[key]
            for key in sorted(decisions)
        },
    }


def _simulation_out(
    review: models.ReservationRecommendationReview,
    *,
    replay: bool,
) -> dict[str, Any]:
    return {
        "recommendation_hash": review.recommendation_hash,
        "simulation_hash": review.simulation_hash,
        "stan": review.status,
        **dict(review.simulation or {}),
        "replay": replay,
    }


def simulate(
    db,
    recommendation_hash: str,
    start: date,
    end: date,
    user,
) -> dict[str, Any]:
    """Persist a PII-free before/after snapshot without changing settings."""
    _validate_range(start, end)
    candidate = _candidate_or_stale(db, recommendation_hash, start, end)
    existing = (
        db.query(models.ReservationRecommendationReview)
        .filter(
            models.ReservationRecommendationReview.recommendation_hash
            == recommendation_hash,
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        if existing.status == "simulated":
            return _simulation_out(existing, replay=True)
        raise _conflict(
            "RECOMMENDATION_ALREADY_DECIDED",
            "Ta rekomendacja ma już zapisaną decyzję.",
        )

    service_id = int(candidate["serwis"]["id"])
    service = (
        db.query(models.GodzinyOtwarcia)
        .filter(models.GodzinyOtwarcia.id == service_id)
        .with_for_update()
        .first()
    )
    if service is None:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Serwis nie jest już dostępny. Odśwież rekomendacje.",
        )
    proposed_thresholds = _updated_thresholds(
        service,
        candidate["segment"],
        int(candidate["proponowane_min"]),
    )
    horizon_start, horizon_end, slots = _future_service_slots(db, service_id)

    # Lazy import avoids the main -> router -> domain initialization cycle.
    import main

    original_thresholds = deepcopy(service.turn_time_progi)
    with db.no_autoflush:
        before = _availability_snapshot(
            main._ocen_przydzial_rezerwacji,
            db,
            slots,
            _SEGMENT_PARTY_SIZE[candidate["segment"]],
        )
        try:
            service.turn_time_progi = proposed_thresholds
            after = _availability_snapshot(
                main._ocen_przydzial_rezerwacji,
                db,
                slots,
                _SEGMENT_PARTY_SIZE[candidate["segment"]],
            )
        finally:
            service.turn_time_progi = original_thresholds

    summary = {
        "sprawdzone_sloty": len(slots),
        "dostepne_przed": before["available"],
        "dostepne_po": after["available"],
        "roznica": after["available"] - before["available"],
        "decyzje_przed": before["decisions"],
        "decyzje_po": after["decisions"],
        "opis": (
            "Snapshot kolejnych 28 dni; istniejące rezerwacje i ustawienia "
            "nie zostały zmienione."
        ),
    }
    simulation = {
        "version": 1,
        "horyzont": {
            "start": str(horizon_start),
            "end": str(horizon_end),
            "dni": SIMULATION_DAYS,
        },
        "summary": summary,
    }
    simulation_hash = _hash({
        "contract": "reservation-turn-time-simulation:v1",
        "recommendation_hash": recommendation_hash,
        "service_id": service_id,
        "segment": candidate["segment"],
        "proposed_thresholds": proposed_thresholds,
        "simulation": simulation,
    })
    review = models.ReservationRecommendationReview(
        recommendation_hash=recommendation_hash,
        simulation_hash=simulation_hash,
        kind="turn_time",
        service_id=service_id,
        segment=candidate["segment"],
        period_start=start,
        period_end=end,
        recommendation=dict(candidate),
        simulation=simulation,
        status="simulated",
        simulated_by_user_id=getattr(user, "id", None),
        simulated_by_login=getattr(user, "login", None),
        created_at=utcnow_naive(),
    )
    db.add(review)
    db.flush()
    return _simulation_out(review, replay=False)


def _payload_value(payload: Any, name: str) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(name)
    return getattr(payload, name, None)


def _payload_date(payload: Any, name: str) -> date:
    value = _payload_value(payload, name)
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            value = None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise _error(
            400,
            "INVALID_RECOMMENDATION_DECISION",
            "Decyzja wymaga poprawnego zakresu dat.",
        )
    return value


def _idempotency_hash(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) < 8 or len(value) > 128:
        raise _error(
            400,
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key musi mieć od 8 do 128 znaków.",
        )
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise _error(
            400,
            "INVALID_IDEMPOTENCY_KEY",
            "Niepoprawny nagłówek Idempotency-Key.",
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_decision_payload(payload: Any) -> dict[str, Any]:
    start = _payload_date(payload, "start")
    end = _payload_date(payload, "end")
    _validate_range(start, end)
    simulation_hash = _payload_value(payload, "simulation_hash")
    decision = _payload_value(payload, "decyzja")
    reason = _payload_value(payload, "powod")
    if not _valid_hash(simulation_hash):
        raise _error(
            400,
            "INVALID_RECOMMENDATION_DECISION",
            "Decyzja wymaga poprawnego identyfikatora symulacji.",
        )
    if decision not in {"accepted", "rejected"}:
        raise _error(
            400,
            "INVALID_RECOMMENDATION_DECISION",
            "Nieznana decyzja dla rekomendacji.",
        )
    if decision == "accepted" and reason != _ACCEPT_REASON:
        raise _error(
            400,
            "INVALID_RECOMMENDATION_DECISION",
            "Przyjęcie wymaga potwierdzenia po symulacji.",
        )
    if decision == "rejected" and reason not in _REJECT_REASONS:
        raise _error(
            400,
            "INVALID_RECOMMENDATION_DECISION",
            "Wybierz poprawny powód odrzucenia rekomendacji.",
        )
    return {
        "start": start,
        "end": end,
        "simulation_hash": simulation_hash,
        "decision": decision,
        "reason": reason,
    }


def _audit_decision(
    db,
    user,
    review: models.ReservationRecommendationReview,
    *,
    before_minutes: int,
    after_minutes: int,
) -> None:
    details = {
        "kind": "turn_time",
        "recommendation_hash": review.recommendation_hash,
        "simulation_hash": review.simulation_hash,
        "service_id": review.service_id,
        "segment": review.segment,
        "period": {
            "start": str(review.period_start),
            "end": str(review.period_end),
        },
        "decision": review.status,
        "reason_code": review.decision_reason,
        "before_minutes": before_minutes,
        "after_minutes": after_minutes,
    }
    db.add(models.AuditLog(
        ts=review.decided_at,
        user_id=getattr(user, "id", None),
        login=getattr(user, "login", None),
        akcja="reservation_recommendation_decision",
        zasob=f"reservation_service:{review.service_id}",
        szczegoly=_canonical_json(details),
    ))


def decide(
    db,
    recommendation_hash: str,
    payload: Any,
    idempotency_key: str,
    user,
) -> dict[str, Any]:
    """Apply one threshold or store a rejection; caller owns commit/rollback."""
    if not _valid_hash(recommendation_hash):
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Rekomendacja jest nieaktualna. Odśwież dane.",
        )
    values = _validate_decision_payload(payload)
    key_hash = _idempotency_hash(idempotency_key)
    fingerprint = _hash({
        "contract": "reservation-recommendation-decision:v1",
        "recommendation_hash": recommendation_hash,
        "start": str(values["start"]),
        "end": str(values["end"]),
        "simulation_hash": values["simulation_hash"],
        "decision": values["decision"],
        "reason": values["reason"],
    })

    replay = (
        db.query(models.ReservationRecommendationReview)
        .filter(
            models.ReservationRecommendationReview.decision_key_hash == key_hash,
        )
        .with_for_update()
        .first()
    )
    if replay is not None:
        if (
            replay.decision_fingerprint is not None
            and secrets.compare_digest(replay.decision_fingerprint, fingerprint)
            and replay.status in {"accepted", "rejected"}
        ):
            return _decision_out(replay, replay=True)
        raise _conflict(
            "IDEMPOTENCY_KEY_REUSED",
            "Ten Idempotency-Key został użyty dla innej decyzji.",
        )

    review = (
        db.query(models.ReservationRecommendationReview)
        .filter(
            models.ReservationRecommendationReview.recommendation_hash
            == recommendation_hash,
        )
        .with_for_update()
        .first()
    )
    if review is None:
        raise _conflict(
            "RECOMMENDATION_NOT_SIMULATED",
            "Najpierw wykonaj aktualną symulację rekomendacji.",
        )
    if review.status != "simulated":
        raise _conflict(
            "RECOMMENDATION_ALREADY_DECIDED",
            "Ta rekomendacja ma już zapisaną decyzję.",
        )
    if review.period_start != values["start"] or review.period_end != values["end"]:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Zakres decyzji nie odpowiada zapisanej symulacji.",
        )
    if not secrets.compare_digest(review.simulation_hash, values["simulation_hash"]):
        raise _conflict(
            "SIMULATION_STALE",
            "Symulacja jest nieaktualna. Policz wpływ ponownie.",
        )

    service = (
        db.query(models.GodzinyOtwarcia)
        .filter(models.GodzinyOtwarcia.id == review.service_id)
        .with_for_update()
        .first()
    )
    if service is None:
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Serwis nie jest już dostępny. Odśwież rekomendacje.",
        )
    candidate = _candidate_or_stale(
        db,
        recommendation_hash,
        values["start"],
        values["end"],
    )
    if (
        int(candidate["serwis"]["id"]) != review.service_id
        or candidate["segment"] != review.segment
    ):
        raise _conflict(
            "RECOMMENDATION_STALE",
            "Zakres rekomendacji zmienił się. Odśwież dane.",
        )

    before_minutes = int(candidate["obecnie_min"])
    after_minutes = before_minutes
    if values["decision"] == "accepted":
        after_minutes = int(candidate["proponowane_min"])
        service.turn_time_progi = _updated_thresholds(
            service,
            review.segment,
            after_minutes,
        )

    review.status = values["decision"]
    review.decision_reason = values["reason"]
    review.decision_key_hash = key_hash
    review.decision_fingerprint = fingerprint
    review.decided_by_user_id = getattr(user, "id", None)
    review.decided_by_login = getattr(user, "login", None)
    review.decided_at = utcnow_naive()
    _audit_decision(
        db,
        user,
        review,
        before_minutes=before_minutes,
        after_minutes=after_minutes,
    )
    db.flush()
    return _decision_out(review, replay=False)
