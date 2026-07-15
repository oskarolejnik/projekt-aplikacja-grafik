"""Wspolny evaluator regul dostepnosci rezerwacji (R3).

Modul jest celowo niezalezny od wyboru stolika. Wylicza serwis, krok slotu,
turn time, pacing oraz jednoczesne oblozenie. Warstwa HTTP moze nastepnie
uruchomic istniejacy silnik ``seating`` i atomowo zapisac oba ledgery.

Odczyty (symulator/widget) sa informacyjne. Kazdy zapis musi ponownie wywolac
evaluator po ``reservation_service.begin_locked_write``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Any, Iterable, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

import models
import reservation_service


WARSAW = ZoneInfo("Europe/Warsaw")
DEFAULT_SLOT_MIN = 120
Channel = Literal["online", "wewnetrzna"]
Intent = Literal["quote", "create", "edit", "simulate", "assign"]

_SCOPE_ORDER = {"global": 0, "channel": 1, "room": 2, "room_channel": 3}
_RULE_ORDER = {
    "date_not_past": 10,
    "local_time": 20,
    "channel": 30,
    "service": 40,
    "slot_step": 50,
    "advance_window": 60,
    "cutoff": 70,
    "party_min": 80,
    "party_max": 90,
    "large_party": 100,
    "pacing_reservations": 110,
    "pacing_covers": 120,
    "concurrent_reservations": 130,
    "concurrent_covers": 140,
    "interval": 150,
}
_BAD_REQUEST_CODES = frozenset({
    "DATE_IN_PAST",
    "INVALID_LOCAL_TIME",
    "INVALID_RESERVATION_INTERVAL",
    "PARTY_SIZE_BELOW_MIN",
    "PARTY_SIZE_ABOVE_MAX",
    "ADVANCE_WINDOW_EXCEEDED",
})
_ASSIGN_RULES = frozenset({
    "local_time",
    "interval",
    "channel",
    "concurrent_reservations",
    "concurrent_covers",
})


def _hm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def _minute(value: time) -> int:
    return value.hour * 60 + value.minute


def _time_from_minute(value: int) -> time:
    value = max(0, min(1439, int(value)))
    return time(value // 60, value % 60)


def _value(source: Any, *names: str, default: Any = None) -> Any:
    if source is None:
        return default
    for name in names:
        if isinstance(source, Mapping) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _positive(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalise_channel(value: str | None) -> Channel:
    raw = (value or "wewnetrzna").strip().lower()
    if raw in {
        "reczna", "internal", "wewnetrzny", "wewnetrzna", "walk_in", "recepcja",
    }:
        return "wewnetrzna"
    if raw == "online":
        return "online"
    raise ValueError("unsupported reservation channel")


def _scope(*, sala_id: int | None = None, kanal: str | None = None) -> dict[str, Any]:
    channel = None if kanal in {None, "", "oba"} else normalise_channel(kanal)
    if sala_id is not None and channel is not None:
        kind = "room_channel"
    elif sala_id is not None:
        kind = "room"
    elif channel is not None:
        kind = "channel"
    else:
        kind = "global"
    return {"type": kind, "sala_id": sala_id, "kanal": channel}


def _source(kind: str, source_id: int | None = None) -> dict[str, Any]:
    return {"type": kind, "id": source_id}


@dataclass(frozen=True)
class ReservationService:
    id: int | None
    name: str | None
    godz_od: time
    godz_do: time
    ostatni_zasiadek: time | None = None
    krok_slotu_min: int | None = None
    domyslny_turn_time_min: int | None = None
    dlugosc_slotu_min: int | None = None
    turn_time_progi: tuple[dict[str, int], ...] = ()
    pacing_okno_min: int | None = None
    pacing_max_rez: int | None = None
    pacing_max_osob: int | None = None
    max_jednoczesnych_rez: int | None = None
    max_jednoczesnych_osob: int | None = None
    bufor_min: int | None = None
    duza_grupa_od: int | None = None
    duza_grupa_tryb: str | None = None
    source: dict[str, Any] = field(default_factory=lambda: _source("service"))

    @property
    def nazwa(self) -> str | None:
        """Adapter dla istniejących wywołań w ``main.py``."""
        return self.name


@dataclass(frozen=True)
class RuleRequest:
    data: date
    godz_od: time
    liczba_osob: int
    kanal: Channel = "wewnetrzna"
    sala_id: int | None = None
    existing_termin_id: int | None = None
    intent: Intent = "quote"
    godz_do: time | None = None
    preserve_existing_room_access: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kanal", normalise_channel(self.kanal))
        if self.intent not in {"quote", "create", "edit", "simulate", "assign"}:
            raise ValueError("unsupported rule evaluation intent")


@dataclass(frozen=True)
class RuleViolation:
    code: str
    rule: str
    scope: dict[str, Any]
    observed: int | None = None
    limit: int | None = None
    projected: int | None = None
    overrideable_by_operator: bool = True
    message: str = ""
    source: dict[str, Any] = field(default_factory=lambda: _source("system"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "code": self.code,
            "scope": dict(self.scope),
            "limit": self.limit,
            "observed": self.observed,
            "projected": self.projected,
            "message": self.message,
            "source": dict(self.source),
            "overrideable_by_operator": self.overrideable_by_operator,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    request: RuleRequest
    decision: Literal["allow", "override_required", "deny"]
    service_id: int | None
    service_name: str | None
    service_start: time | None
    service_end: time | None
    krok_slotu_min: int
    turn_time_min: int
    buffer_min: int
    godz_do: time | None
    checks: tuple[dict[str, Any], ...] = ()
    violations: tuple[RuleViolation, ...] = ()
    applied_rules: tuple[dict[str, Any], ...] = ()
    resource_allocation: Literal["not_simulated"] = "not_simulated"

    @property
    def available(self) -> bool:
        return self.decision == "allow"

    @property
    def can_override(self) -> bool:
        return self.decision == "override_required"

    @property
    def code(self) -> str | None:
        return self.violations[0].code if self.violations else None

    @property
    def rule(self) -> str | None:
        return self.violations[0].rule if self.violations else None

    def to_dict(self) -> dict[str, Any]:
        service = None
        if self.service_start is not None and self.service_end is not None:
            service = {
                "id": self.service_id,
                "name": self.service_name,
                "godz_od": _hm(self.service_start),
                "godz_do": _hm(self.service_end),
                "krok_slotu_min": self.krok_slotu_min,
                "turn_time_min": self.turn_time_min,
            }
        return {
            "available": self.available,
            "decision": self.decision,
            "code": self.code,
            "rule": self.rule,
            "service": service,
            "visit_end": _hm(self.godz_do),
            "godz_do": _hm(self.godz_do),
            "krok_slotu_min": self.krok_slotu_min,
            "turn_time_min": self.turn_time_min,
            "buffer_min": self.buffer_min,
            "checks": [dict(item) for item in self.checks],
            "violations": [item.to_dict() for item in self.violations],
            "applied_rules": [dict(item) for item in self.applied_rules],
            "can_override": self.can_override,
            "resource_allocation": self.resource_allocation,
        }


@dataclass(frozen=True)
class _Setting:
    value: Any
    scope: dict[str, Any]
    source: dict[str, Any]


def _service_from(source: Any, *, inherited: Any = None, exception: bool = False) -> ReservationService:
    def pick(*names: str, default: Any = None) -> Any:
        own = _value(source, *names, default=None)
        return own if own is not None else _value(inherited, *names, default=default)

    raw_progi = pick("turn_time_progi", default=()) or ()
    progi = []
    for item in raw_progi:
        if not isinstance(item, Mapping):
            continue
        upper = _positive(item.get("do_osob"))
        minutes = _positive(item.get("min"))
        if upper and minutes:
            progi.append({"do_osob": upper, "min": minutes})
    progi.sort(key=lambda item: item["do_osob"])
    source_id = _value(source, "id")
    service_id = pick("serwis_id", default=None) if exception else source_id
    if service_id is None and inherited is not None:
        service_id = _value(inherited, "id")
    return ReservationService(
        id=service_id,
        name=pick("nazwa", "name"),
        godz_od=pick("godz_od"),
        godz_do=pick("godz_do"),
        ostatni_zasiadek=pick("ostatni_zasiadek"),
        krok_slotu_min=pick("krok_slotu_min"),
        domyslny_turn_time_min=pick("domyslny_turn_time_min"),
        dlugosc_slotu_min=pick("dlugosc_slotu_min"),
        turn_time_progi=tuple(progi),
        pacing_okno_min=pick("pacing_okno_min"),
        pacing_max_rez=pick("pacing_max_rez"),
        pacing_max_osob=pick("pacing_max_osob"),
        max_jednoczesnych_rez=pick("max_jednoczesnych_rez"),
        max_jednoczesnych_osob=pick("max_jednoczesnych_osob"),
        bufor_min=pick("bufor_min"),
        duza_grupa_od=pick("duza_grupa_od"),
        duza_grupa_tryb=pick("duza_grupa_tryb"),
        source=_source("exception" if exception else "service", source_id),
    )


def _exception_rows(db, booking_date: date) -> list[Any]:
    return db.query(models.WyjatekKalendarza).filter(
        models.WyjatekKalendarza.data == booking_date,
    ).order_by(models.WyjatekKalendarza.id).all()


def _base_service_rows(db, booking_date: date) -> list[Any]:
    return db.query(models.GodzinyOtwarcia).filter(
        models.GodzinyOtwarcia.dzien_tygodnia == booking_date.weekday(),
        models.GodzinyOtwarcia.aktywny.is_(True),
    ).order_by(models.GodzinyOtwarcia.godz_od, models.GodzinyOtwarcia.id).all()


def _matching_inherited_service(exception: Any, base_rows: Sequence[Any]) -> Any | None:
    service_id = _value(exception, "serwis_id")
    if service_id is not None:
        return next((row for row in base_rows if row.id == service_id), None)
    name = (_value(exception, "nazwa", default="") or "").strip().casefold()
    if name:
        named = [row for row in base_rows if (row.nazwa or "").strip().casefold() == name]
        if len(named) == 1:
            return named[0]
    start = _value(exception, "godz_od")
    if start is not None:
        overlapping = [
            row for row in base_rows
            if row.godz_od <= start <= (row.ostatni_zasiadek or row.godz_do)
        ]
        if len(overlapping) == 1:
            return overlapping[0]
    return base_rows[0] if len(base_rows) == 1 else None


def serwisy_dnia(db, booking_date: date) -> tuple[ReservationService, ...]:
    """Rozwiazuje serwisy dnia bez niejawnego dziedziczenia z pierwszego z wielu serwisow."""
    base_rows = _base_service_rows(db, booking_date)
    exceptions = _exception_rows(db, booking_date)
    if any((_value(row, "typ", default="") or "").strip() == "blackout" for row in exceptions):
        return ()
    special = [
        row for row in exceptions
        if (_value(row, "typ", default="") or "").strip() == "godziny_specjalne"
        and _value(row, "godz_od") is not None
        and _value(row, "godz_do") is not None
    ]
    if special:
        result = [
            _service_from(
                row,
                inherited=_matching_inherited_service(row, base_rows),
                exception=True,
            )
            for row in special
        ]
    else:
        result = [_service_from(row) for row in base_rows]
    return tuple(sorted(result, key=lambda row: (row.godz_od, row.id or 0)))


def serwis_dla_godziny(
    db,
    booking_date: date,
    start: time,
    *,
    strict: bool = True,
) -> ReservationService | None:
    services = serwisy_dnia(db, booking_date)
    for service in services:
        last = service.ostatni_zasiadek or service.godz_do
        if service.godz_od <= start <= last:
            return service
    return None if strict or not services else services[0]


def krok_slotu(service: ReservationService | Any | None) -> int:
    return (
        _positive(_value(service, "krok_slotu_min"))
        or _positive(_value(service, "dlugosc_slotu_min"))
        or DEFAULT_SLOT_MIN
    )


def turn_time(service: ReservationService | Any | None, party_size: int) -> int:
    base = (
        _positive(_value(service, "domyslny_turn_time_min"))
        or _positive(_value(service, "dlugosc_slotu_min"))
        or DEFAULT_SLOT_MIN
    )
    raw = _value(service, "turn_time_progi", default=()) or ()
    thresholds = []
    for item in raw:
        upper = _positive(_value(item, "do_osob"))
        minutes = _positive(_value(item, "min"))
        if upper and minutes:
            thresholds.append((upper, minutes))
    thresholds.sort()
    if not thresholds:
        return base
    party = max(1, int(party_size or 1))
    for upper, minutes in thresholds:
        if party <= upper:
            return minutes
    return thresholds[-1][1]


def sloty_dnia(db, booking_date: date) -> tuple[tuple[time, ReservationService], ...]:
    slots: dict[time, ReservationService] = {}
    for service in serwisy_dnia(db, booking_date):
        step = krok_slotu(service)
        current = _minute(service.godz_od)
        last = _minute(service.ostatni_zasiadek or service.godz_do)
        while current <= last and current < 1440:
            value = _time_from_minute(current)
            slots.setdefault(value, service)
            current += step
    return tuple((value, slots[value]) for value in sorted(slots))


def _local_time_status(booking_date: date, start: time) -> Literal["valid", "nonexistent", "ambiguous"]:
    naive = datetime.combine(booking_date, start)

    def candidate(fold: int) -> tuple[bool, Any]:
        aware = naive.replace(tzinfo=WARSAW, fold=fold)
        back = aware.astimezone(timezone.utc).astimezone(WARSAW).replace(tzinfo=None)
        return back == naive, aware.utcoffset()

    valid0, offset0 = candidate(0)
    valid1, offset1 = candidate(1)
    if not valid0 and not valid1:
        return "nonexistent"
    if valid0 and valid1 and offset0 != offset1:
        return "ambiguous"
    return "valid"


def _now_local(now: datetime | None) -> datetime:
    value = now or datetime.now(WARSAW)
    if value.tzinfo is None:
        return value.replace(tzinfo=WARSAW)
    return value.astimezone(WARSAW)


def _lokal_config(db) -> Any | None:
    model = getattr(models, "LokalConfig", None)
    return db.query(model).first() if model is not None else None


def _room(db, sala_id: int | None) -> Any | None:
    if sala_id is None:
        return None
    return db.get(models.SalaRezerwacyjna, sala_id)


def _rule_rows(db) -> list[Any]:
    model = getattr(models, "RegulaDostepnosciRezerwacji", None)
    if model is None:
        return []
    return db.query(model).order_by(model.id).all()


_POLICY_ALIASES = {
    "pacing_window_min": ("pacing_okno_min",),
    "pacing_max_reservations": ("pacing_max_rez",),
    "pacing_max_covers": ("pacing_max_osob",),
    "concurrent_max_reservations": (
        "max_jednoczesnych_rez", "limit_jednoczesnych_rez",
    ),
    "concurrent_max_covers": (
        "max_jednoczesnych_osob", "limit_jednoczesnych_osob",
    ),
    "buffer_min": ("bufor_min", "domyslny_bufor_min"),
    "advance_days": ("okno_wyprzedzenia_dni", "rez_okno_wyprzedzenia_dni"),
    "cutoff_min": ("cutoff_min", "rez_cutoff_min"),
    "party_min": ("min_grupa", "rez_min_grupa_online"),
    "party_max": ("max_grupa", "rez_max_grupa_online"),
    "large_party_from": ("duza_grupa_od",),
    "large_party_mode": ("duza_grupa_tryb",),
}


def _read_policy_value(source: Any, key: str) -> Any:
    return _value(source, *_POLICY_ALIASES[key])


def _resolve_policy(
    db,
    request: RuleRequest,
    service: ReservationService | None,
    room: Any | None,
) -> dict[str, _Setting]:
    settings: dict[str, _Setting] = {}

    def apply(source_obj: Any, *, kind: str, source_id: int | None, scope: dict[str, Any], keys: Iterable[str]) -> None:
        for key in keys:
            value = _read_policy_value(source_obj, key)
            if value is not None:
                settings[key] = _Setting(value=value, scope=scope, source=_source(kind, source_id))

    # Historyczne pola LokalConfig sa polityka kanalu online, nie wewnetrznego.
    config = _lokal_config(db)
    if request.kanal == "online" and config is not None:
        apply(
            config,
            kind="legacy",
            source_id=_value(config, "id"),
            scope=_scope(kanal="online"),
            keys=("advance_days", "cutoff_min", "party_min", "party_max", "buffer_min"),
        )

    if service is not None:
        apply(
            service,
            kind="service",
            source_id=service.id,
            scope=_scope(),
            keys=(
                "pacing_window_min", "pacing_max_reservations", "pacing_max_covers",
                "concurrent_max_reservations", "concurrent_max_covers", "buffer_min",
                "large_party_from", "large_party_mode",
            ),
        )

    if room is not None:
        apply(
            room,
            kind="room",
            source_id=_value(room, "id"),
            scope=_scope(sala_id=request.sala_id),
            keys=("concurrent_max_reservations", "concurrent_max_covers", "buffer_min"),
        )

    matching = []
    for row in _rule_rows(db):
        row_service = _value(row, "serwis_id")
        row_room = _value(row, "sala_id")
        row_channel = (_value(row, "kanal", default="oba") or "oba").strip().lower()
        if row_service is not None and (service is None or row_service != service.id):
            continue
        if row_room is not None and row_room != request.sala_id:
            continue
        if row_channel != "oba" and normalise_channel(row_channel) != request.kanal:
            continue
        specificity = sum((row_service is not None, row_room is not None, row_channel != "oba"))
        matching.append((specificity, bool(row_service), bool(row_room), row_channel != "oba", row.id, row))
    for *_sort, row in sorted(matching, key=lambda item: item[:-1]):
        row_room = _value(row, "sala_id")
        raw_channel = (_value(row, "kanal", default="oba") or "oba").strip().lower()
        apply(
            row,
            kind="override",
            source_id=_value(row, "id"),
            scope=_scope(sala_id=row_room, kanal=raw_channel),
            keys=_POLICY_ALIASES,
        )
    return settings


def _setting(settings: Mapping[str, _Setting], key: str) -> _Setting:
    return settings.get(key, _Setting(None, _scope(), _source("default")))


def _check(
    *,
    rule: str,
    code: str,
    passed: bool,
    message: str,
    scope: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    observed: int | None = None,
    limit: int | None = None,
    projected: int | None = None,
    overrideable: bool = True,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "code": code,
        "scope": dict(scope or _scope()),
        "limit": limit,
        "observed": observed,
        "projected": projected,
        "passed": bool(passed),
        "message": message,
        "source": dict(source or _source("system")),
        "overrideable_by_operator": bool(overrideable),
    }


def _scope_matches(row: Any, scope: Mapping[str, Any], channel: Channel, sala_id: int | None) -> bool:
    kind = scope.get("type") or "global"
    row_channel = _value(row, "kanal")
    row_room = _value(row, "sala_id")
    channel_ok = row_channel is not None and normalise_channel(row_channel) == channel
    room_ok = row_room is not None and row_room == sala_id
    if kind == "channel":
        return channel_ok
    if kind == "room":
        return room_ok
    if kind == "room_channel":
        return channel_ok and room_ok
    return True


def _occupancy_rows(
    db,
    booking_date: date,
    *,
    start_minute: int | None = None,
    end_minute: int | None = None,
) -> list[Any]:
    """Odczytuje ledger i przedłuża aktywne wizyty hosta na oceniane okno.

    Minutowy ledger opisuje planowany czas wizyty. Fazy ``posadzony``–``oplacony``
    są jednak stanem live i muszą uczestniczyć w limitach jednoczesnych tak
    długo, jak gość faktycznie pozostaje przy stole. Syntetyczne wiersze mają
    ten sam ``termin_id``, więc nie dublują istniejącego fragmentu ledgera.
    """
    model = getattr(models, "RezerwacjaOblozenieLedger", None)
    if model is None:
        return []
    rows = db.query(model).filter(model.data == booking_date).all()
    if (
        start_minute is None
        or end_minute is None
        or end_minute <= start_minute
    ):
        return rows

    existing_meta: dict[int, Any] = {}
    for row in rows:
        termin_id = _value(row, "termin_id")
        if termin_id is not None:
            existing_meta.setdefault(termin_id, row)

    live = db.query(
        models.Termin.id,
        models.Termin.liczba_osob,
        models.Termin.kanal,
        models.Stolik.sala_id,
    ).outerjoin(
        models.Stolik, models.Stolik.id == models.Termin.stolik_id,
    ).filter(
        models.Termin.data == booking_date,
        models.Termin.rodzaj == "stolik",
        models.Termin.status.in_(reservation_service.ACTIVE_STATUSES),
        models.Termin.faza_hosta.in_(reservation_service.LIVE_HOST_PHASES),
    ).all()
    for termin_id, covers, raw_channel, table_room_id in live:
        meta = existing_meta.get(termin_id)
        room_id = _value(meta, "sala_id", default=table_room_id)
        channel = _value(
            meta,
            "kanal",
            default=reservation_service.normalise_reservation_channel(raw_channel),
        )
        rows.extend(
            SimpleNamespace(
                termin_id=termin_id,
                minute=minute,
                sala_id=room_id,
                kanal=channel,
                covers=max(0, int(covers or 0)),
            )
            for minute in range(start_minute, end_minute)
        )
    return rows


def _concurrent_usage(
    rows: Iterable[Any],
    *,
    start_minute: int,
    end_minute: int,
    channel: Channel,
    sala_id: int | None,
    scope: Mapping[str, Any],
    exclude_termin_id: int | None = None,
) -> tuple[int, int]:
    by_minute: dict[int, dict[Any, int]] = {}
    for row in rows:
        minute = _value(row, "minute")
        termin_id = _value(row, "termin_id", "id")
        if minute is None or not start_minute <= int(minute) < end_minute:
            continue
        if exclude_termin_id is not None and termin_id == exclude_termin_id:
            continue
        if not _scope_matches(row, scope, channel, sala_id):
            continue
        by_minute.setdefault(int(minute), {})[termin_id] = max(
            0, int(_value(row, "covers", default=0) or 0),
        )
    reservations = max((len(items) for items in by_minute.values()), default=0)
    covers = max((sum(items.values()) for items in by_minute.values()), default=0)
    return reservations, covers


def _pacing_rows(db, booking_date: date) -> list[Any]:
    model = getattr(models, "RezerwacjaPacingLedger", None)
    if model is None:
        return []
    return db.query(model).filter(model.data == booking_date).all()


def _occupancy_meta(rows: Iterable[Any]) -> dict[int, Any]:
    result = {}
    for row in rows:
        termin_id = _value(row, "termin_id")
        if termin_id is not None:
            result.setdefault(termin_id, row)
    return result


def _pacing_usage(
    rows: Iterable[Any],
    occupancy_meta: Mapping[int, Any],
    *,
    bucket_start: int,
    bucket_end: int,
    channel: Channel,
    sala_id: int | None,
    scope: Mapping[str, Any],
    exclude_termin_id: int | None,
) -> tuple[int, int]:
    reservations: dict[int, int] = {}
    for row in rows:
        termin_id = _value(row, "termin_id")
        minute = _value(row, "start_minute")
        if termin_id is None or minute is None or not bucket_start <= int(minute) < bucket_end:
            continue
        if exclude_termin_id is not None and termin_id == exclude_termin_id:
            continue
        if scope.get("type") != "global":
            meta = occupancy_meta.get(termin_id)
            if meta is None or not _scope_matches(meta, scope, channel, sala_id):
                continue
        reservations[termin_id] = max(0, int(_value(row, "covers", default=0) or 0))
    return len(reservations), sum(reservations.values())


def _sort_checks(checks: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(sorted(
        checks,
        key=lambda item: (
            _RULE_ORDER.get(item["rule"], 999),
            _SCOPE_ORDER.get(item["scope"].get("type"), 99),
            item["code"],
        ),
    ))


def _violations(checks: Iterable[dict[str, Any]]) -> tuple[RuleViolation, ...]:
    return tuple(
        RuleViolation(
            code=item["code"],
            rule=item["rule"],
            scope=item["scope"],
            observed=item["observed"],
            limit=item["limit"],
            projected=item["projected"],
            overrideable_by_operator=item["overrideable_by_operator"],
            message=item["message"],
            source=item["source"],
        )
        for item in checks if not item["passed"]
    )


def evaluate_reservation_rules(
    db,
    request: RuleRequest,
    *,
    now: datetime | None = None,
) -> RuleEvaluation:
    """Ocenia reguly bez wyboru ani zajecia stolika."""
    local_now = _now_local(now)
    services = serwisy_dnia(db, request.data)
    service = serwis_dla_godziny(db, request.data, request.godz_od, strict=True)
    room = _room(db, request.sala_id)
    policy = _resolve_policy(db, request, service, room)
    step = krok_slotu(service)
    duration = turn_time(service, request.liczba_osob)
    start_minute = _minute(request.godz_od)
    configured_end_minute = start_minute + duration
    # Jawny koniec moze wydluzyc wizyte, ale nie moze skrocic zajetosci ponizej
    # turn-time serwisu i w ten sposob ominac limitow jednoczesnych rezerwacji.
    raw_end_minute = max(
        _minute(request.godz_do) if request.godz_do is not None else 0,
        configured_end_minute,
    )
    end_minute = min(1440, raw_end_minute)
    end_value = _time_from_minute(end_minute) if end_minute < 1440 else None
    buffer_min = _positive(_setting(policy, "buffer_min").value) or 0
    checks: list[dict[str, Any]] = []

    checks.append(_check(
        rule="date_not_past", code="DATE_IN_PAST",
        # Kanał wewnętrzny służy także migracji i uzupełnianiu historii. Widget
        # gościa nigdy nie może utworzyć rezerwacji wstecz.
        passed=request.kanal != "online" or request.data >= local_now.date(),
        observed=(local_now.date() - request.data).days if request.data < local_now.date() else 0,
        limit=0,
        message="Nie mozna utworzyc rezerwacji w przeszlosci.",
        overrideable=False,
    ))
    time_status = _local_time_status(request.data, request.godz_od)
    checks.append(_check(
        rule="local_time", code="INVALID_LOCAL_TIME",
        passed=time_status == "valid",
        message=(
            "Godzina jest jednoznaczna w strefie Europe/Warsaw."
            if time_status == "valid"
            else (
                "Ta godzina nie istnieje przy zmianie czasu."
                if time_status == "nonexistent"
                else "Ta godzina jest niejednoznaczna przy zmianie czasu."
            )
        ),
        overrideable=False,
    ))
    whole_minute = (
        request.godz_od.second == 0
        and request.godz_od.microsecond == 0
        and (
            request.godz_do is None
            or (
                request.godz_do.second == 0
                and request.godz_do.microsecond == 0
            )
        )
    )
    checks.append(_check(
        rule="interval", code="INVALID_RESERVATION_INTERVAL",
        passed=whole_minute and raw_end_minute < 1440,
        observed=raw_end_minute,
        limit=1439,
        message=(
            "Godziny rezerwacji musza miec dokladnosc do pelnej minuty."
            if not whole_minute
            else "Wizyta nie moze przechodzic przez polnoc."
        ),
        overrideable=False,
    ))

    if room is not None:
        enabled_field = "online_aktywna" if request.kanal == "online" else "wewnetrzna_aktywna"
        room_active = _value(room, "aktywna", default=True) is not False
        channel_active = _value(room, enabled_field, default=True) is not False
        # Wyłączenie sali blokuje nowe przydziały, ale nie może uniemożliwiać
        # korekty rezerwacji, która już ma w niej historyczny przydział.
        preserve_historical_assignment = (
            request.intent == "edit"
            and request.existing_termin_id is not None
            and request.preserve_existing_room_access
        )
        enabled = channel_active and (room_active or preserve_historical_assignment)
        checks.append(_check(
            rule="channel", code="CHANNEL_NOT_ALLOWED",
            passed=bool(enabled),
            scope=_scope(sala_id=request.sala_id, kanal=request.kanal),
            source=_source("room", request.sala_id),
            message="Wybrana sala nie przyjmuje rezerwacji w tym kanale.",
        ))

    explicit_blackout = any(
        (_value(row, "typ", default="") or "").strip() == "blackout"
        for row in _exception_rows(db, request.data)
    )
    if service is None:
        if request.kanal == "online":
            checks.append(_check(
                rule="service",
                code="DATE_CLOSED" if not services else "OUTSIDE_SERVICE_WINDOW",
                passed=False,
                message=(
                    "W tym dniu nie ma aktywnego serwisu rezerwacyjnego."
                    if not services else "Godzina jest poza oknem aktywnego serwisu."
                ),
            ))
        elif explicit_blackout:
            checks.append(_check(
                rule="service", code="DATE_CLOSED", passed=False,
                source=_source("calendar_exception"),
                message="Ten dzien jest oznaczony jako zamkniety.",
            ))
        elif services:
            checks.append(_check(
                rule="service", code="OUTSIDE_SERVICE_WINDOW", passed=False,
                message="Godzina jest poza oknem aktywnego serwisu.",
            ))
        # Brak jakiejkolwiek konfiguracji pozostaje permissive dla wewnetrznego legacy.
    else:
        checks.append(_check(
            rule="service", code="OUTSIDE_SERVICE_WINDOW", passed=True,
            source=service.source,
            message="Godzina nalezy do aktywnego serwisu.",
        ))
        if request.kanal == "online":
            offset = start_minute - _minute(service.godz_od)
            aligned = offset >= 0 and offset % step == 0
            checks.append(_check(
                rule="slot_step", code="SLOT_NOT_OFFERED", passed=aligned,
                observed=offset, limit=step,
                source=service.source,
                message="Ta godzina nie jest oferowanym slotem online.",
            ))

    advance = _setting(policy, "advance_days")
    max_days = _positive(advance.value)
    if max_days:
        observed_days = (request.data - local_now.date()).days
        checks.append(_check(
            rule="advance_window", code="ADVANCE_WINDOW_EXCEEDED",
            passed=observed_days <= max_days,
            observed=observed_days, projected=observed_days, limit=max_days,
            scope=advance.scope, source=advance.source,
            message="Termin wykracza poza dozwolone okno wyprzedzenia.",
        ))

    cutoff = _setting(policy, "cutoff_min")
    cutoff_value = _positive(cutoff.value) or 0
    # Nawet cutoff=0 nie oznacza mozliwosci rezerwowania godziny, ktora juz
    # minela dzisiaj. Dla obslugi jest to jawnie nadpisywalne ostrzezenie;
    # historyczne wpisy z poprzednich dni pozostaja obslugiwane przez legacy.
    if request.data >= local_now.date() and time_status == "valid":
        target = datetime.combine(request.data, request.godz_od).replace(tzinfo=WARSAW)
        minutes_ahead = int((target - local_now).total_seconds() // 60)
        checks.append(_check(
            rule="cutoff", code="BOOKING_CUTOFF_REACHED",
            passed=minutes_ahead >= cutoff_value,
            observed=minutes_ahead, projected=minutes_ahead, limit=cutoff_value,
            scope=cutoff.scope, source=cutoff.source,
            message="Jest juz za pozno na rezerwacje w tym terminie.",
        ))

    party_min = _setting(policy, "party_min")
    min_value = _positive(party_min.value) or 1
    checks.append(_check(
        rule="party_min", code="PARTY_SIZE_BELOW_MIN",
        passed=request.liczba_osob >= min_value,
        observed=request.liczba_osob, projected=request.liczba_osob, limit=min_value,
        scope=party_min.scope, source=party_min.source,
        message="Grupa jest mniejsza niz dozwolone minimum.",
    ))
    party_max = _setting(policy, "party_max")
    max_value = _positive(party_max.value)
    if max_value:
        checks.append(_check(
            rule="party_max", code="PARTY_SIZE_ABOVE_MAX",
            passed=request.liczba_osob <= max_value,
            observed=request.liczba_osob, projected=request.liczba_osob, limit=max_value,
            scope=party_max.scope, source=party_max.source,
            message="Grupa przekracza dozwolone maksimum.",
        ))

    large_from = _setting(policy, "large_party_from")
    large_threshold = _positive(large_from.value)
    large_mode = str(_setting(policy, "large_party_mode").value or "online").strip().lower()
    if large_threshold and request.liczba_osob >= large_threshold:
        if large_mode in {"do_zatwierdzenia", "approval", "zatwierdzenie"}:
            checks.append(_check(
                rule="large_party", code="LARGE_PARTY_APPROVAL_REQUIRED", passed=False,
                observed=request.liczba_osob, projected=request.liczba_osob, limit=large_threshold,
                scope=large_from.scope, source=large_from.source,
                message="Duza grupa wymaga jawnego zatwierdzenia operatora.",
            ))
        elif large_mode in {"tylko_telefonicznie", "phone_only", "telefon"} and request.kanal == "online":
            checks.append(_check(
                rule="large_party", code="LARGE_PARTY_PHONE_ONLY", passed=False,
                observed=request.liczba_osob, projected=request.liczba_osob, limit=large_threshold,
                scope=large_from.scope, source=large_from.source,
                message="Tak duza grupa moze byc przyjeta tylko przez obsluge.",
                overrideable=False,
            ))

    occupancy = _occupancy_rows(
        db,
        request.data,
        start_minute=start_minute,
        end_minute=end_minute,
    )
    pacing_rows = _pacing_rows(db, request.data)
    meta = _occupancy_meta(occupancy)
    pacing_window = _positive(_setting(policy, "pacing_window_min").value) or step
    anchor = _minute(service.godz_od) if service is not None else 0
    bucket_index = max(0, (start_minute - anchor) // pacing_window)
    bucket_start = anchor + bucket_index * pacing_window
    bucket_end = min(1440, bucket_start + pacing_window)

    for key, rule, code, is_covers in (
        ("pacing_max_reservations", "pacing_reservations", "PACING_RESERVATION_LIMIT", False),
        ("pacing_max_covers", "pacing_covers", "PACING_COVERS_LIMIT", True),
    ):
        setting = _setting(policy, key)
        limit = _positive(setting.value)
        if not limit:
            continue
        reservations, covers = _pacing_usage(
            pacing_rows, meta,
            bucket_start=bucket_start, bucket_end=bucket_end,
            channel=request.kanal, sala_id=request.sala_id, scope=setting.scope,
            exclude_termin_id=request.existing_termin_id,
        )
        observed = covers if is_covers else reservations
        projected = observed + (request.liczba_osob if is_covers else 1)
        checks.append(_check(
            rule=rule, code=code, passed=projected <= limit,
            observed=observed, projected=projected, limit=limit,
            scope=setting.scope, source=setting.source,
            message=(
                "Osiagnieto limit nowych osob w oknie pacingu."
                if is_covers else "Osiagnieto limit nowych rezerwacji w oknie pacingu."
            ),
        ))

    if end_minute > start_minute:
        for key, rule, code, is_covers in (
            ("concurrent_max_reservations", "concurrent_reservations", "CONCURRENT_RESERVATION_LIMIT", False),
            ("concurrent_max_covers", "concurrent_covers", "CONCURRENT_COVERS_LIMIT", True),
        ):
            setting = _setting(policy, key)
            limit = _positive(setting.value)
            if not limit:
                continue
            reservations, covers = _concurrent_usage(
                occupancy,
                start_minute=start_minute, end_minute=end_minute,
                channel=request.kanal, sala_id=request.sala_id, scope=setting.scope,
                exclude_termin_id=request.existing_termin_id,
            )
            observed = covers if is_covers else reservations
            projected = observed + (request.liczba_osob if is_covers else 1)
            checks.append(_check(
                rule=rule, code=code, passed=projected <= limit,
                observed=observed, projected=projected, limit=limit,
                scope=setting.scope, source=setting.source,
                message=(
                    "Osiagnieto limit jednoczesnie obslugiwanych osob."
                    if is_covers else "Osiagnieto limit jednoczesnych rezerwacji."
                ),
            ))

    # Przydzielenie zasobu do istniejacej rezerwacji nie jest ponowna proba
    # jej sprzedazy. Dlatego nie blokujemy hosta historycznym cutoffem, limitem
    # wielkosci grupy, pacingiem ani zmiana okna serwisu. Nadal obowiazuja
    # reguly bezpieczenstwa samego przydzialu: poprawny czas, kanal sali i
    # jednoczesna pojemnosc operacyjna.
    if request.intent == "assign":
        checks = [item for item in checks if item["rule"] in _ASSIGN_RULES]

    ordered_checks = _sort_checks(checks)
    violations = _violations(ordered_checks)
    if not violations:
        decision: Literal["allow", "override_required", "deny"] = "allow"
    elif all(item.overrideable_by_operator for item in violations):
        decision = "override_required"
    else:
        decision = "deny"
    applied = tuple(
        {
            "key": key,
            "value": setting.value,
            "scope": dict(setting.scope),
            "source": dict(setting.source),
        }
        for key, setting in sorted(policy.items())
    )
    return RuleEvaluation(
        request=request,
        decision=decision,
        service_id=service.id if service else None,
        service_name=service.name if service else None,
        service_start=service.godz_od if service else None,
        service_end=service.godz_do if service else None,
        krok_slotu_min=step,
        turn_time_min=duration,
        buffer_min=buffer_min,
        godz_do=end_value,
        checks=ordered_checks,
        violations=violations,
        applied_rules=applied,
    )


class _AvailabilityAdapter:
    def __init__(self, evaluation: RuleEvaluation) -> None:
        self.evaluation = evaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.evaluation.to_dict(),
            "candidates": [],
            "alternatives": [],
        }


def evaluation_to_reservation_error(evaluation: RuleEvaluation) -> reservation_service.ReservationError:
    if not evaluation.violations:
        raise ValueError("allowed evaluation cannot be converted to ReservationError")
    first = evaluation.violations[0]
    error = reservation_service.ReservationError(
        400 if first.code in _BAD_REQUEST_CODES else 409,
        first.code,
        first.message,
        rule=first.rule,
    )
    error.availability = _AvailabilityAdapter(evaluation)
    return error


def enforce_rule_evaluation(
    evaluation: RuleEvaluation,
    *,
    override: bool = False,
    can_override: bool = False,
) -> RuleEvaluation:
    """Wymusza decyzje. Uprawnienie i powod override waliduje warstwa endpointu."""
    if evaluation.decision == "allow":
        return evaluation
    if override and can_override and evaluation.decision == "override_required":
        return evaluation
    if override and not can_override:
        error = reservation_service.ReservationError(
            403,
            "OVERRIDE_FORBIDDEN",
            "Brak uprawnienia do przekraczania regul rezerwacji.",
            rule="override",
        )
        error.availability = _AvailabilityAdapter(evaluation)
        raise error
    raise evaluation_to_reservation_error(evaluation)


# Czytelne aliasy dla warstwy integracyjnej.
ReservationRuleInput = RuleRequest
evaluate = evaluate_reservation_rules
enforce = enforce_rule_evaluation
