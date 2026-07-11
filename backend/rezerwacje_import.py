"""Jednorazowa rekonsyliacja legacy rezerwacji z kanonicznym ``Termin``.

Moduł celowo nie udostępnia endpointu HTTP i nie wysyła wiadomości.  Normalizuje
zewnętrzne wpisy do małego kontraktu, porównuje je bez ujawniania PII w raporcie
i opcjonalnie dodaje wyłącznie jednoznacznie brakujące rezerwacje.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models


WARSAW = ZoneInfo("Europe/Warsaw")
UTC = timezone.utc
SOURCE_TYPES = frozenset({"google", "ical"})
REPORT_CATEGORIES = (
    "matched",
    "missing_in_termin",
    "changed",
    "possible_duplicate",
    "source_missing",
    "invalid_external",
    "canonical_only",
)
_PARTY_SIZE_RE = re.compile(
    r"(?:liczba\s+os[oó]b|liczba\s+go[sś]ci|osoby|go[sś]cie)\s*[:=\-]\s*(\d+)",
    re.IGNORECASE,
)
_COMMON_SUMMARY_PREFIX_RE = re.compile(
    r"^\s*(?:rezerwacja(?:\s+stolika)?|booking)\s*[:\-–—]\s*",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?:telefon|tel\.?)\s*[:=]\s*(\+?\d[\d\s().-]{5,24}\d)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(
    r"(?:e-?mail)\s*[:=]\s*([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
_SAFE_DESCRIPTION_LINES = frozenset(
    {"rezerwacja", "rezerwacja stolika", "dane rezerwacji"}
)
_EMPTY_NOTE_LINE_RE = re.compile(
    r"(?:uwagi|notatka|alergi(?:a|e)|specjalne\s+(?:życzenia|prosby|prośby)|"
    r"special\s+requests?)\s*[:=]\s*(?:-|brak|nie|none|n/?a)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExternalReservation:
    """Znormalizowany aktywny wpis z zewnętrznego kalendarza.

    ``guest_name`` jest potrzebne wyłącznie do zapisu i wewnętrznego wykrywania
    możliwych duplikatów. Nigdy nie trafia do raportu rekonsyliacji.
    """

    source_type: str
    source_external_id: str = field(repr=False)
    starts_at: datetime
    ends_at: datetime
    party_size: int
    guest_name: str = field(repr=False)
    phone: str | None = field(default=None, repr=False)
    email: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError("unsupported source_type")
        if not self.source_external_id:
            raise ValueError("source_external_id is required")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("external datetimes must be timezone-aware")
        if self.ends_at.astimezone(UTC) <= self.starts_at.astimezone(UTC):
            raise ValueError("ends_at must be after starts_at")
        if (
            self.starts_at.utcoffset() != self.ends_at.utcoffset()
            or self.starts_at.fold
            or self.ends_at.fold
        ):
            raise ValueError("unsupported_dst_transition")
        if self.party_size <= 0:
            raise ValueError("party_size must be positive")
        if not self.guest_name.strip():
            raise ValueError("guest_name is required")


@dataclass(frozen=True)
class InvalidExternalReservation:
    """Techniczny błąd wpisu bez jego treści ani innych danych gościa."""

    source_type: str
    code: str
    occurs_at: datetime | None = None
    source_external_id: str | None = field(default=None, repr=False)
    party_size: int | None = None


@dataclass(frozen=True)
class NormalizedExternalBatch:
    """Wynik adaptera źródła, gotowy do bezpiecznej rekonsyliacji."""

    source_type: str
    records: tuple[ExternalReservation, ...] = ()
    invalid: tuple[InvalidExternalReservation, ...] = ()
    received_count: int = 0
    source_status: str = "ok"
    source_error_code: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError("unsupported source_type")
        if self.source_status not in {"ok", "error"}:
            raise ValueError("source_status must be ok or error")


def google_source_external_id(calendar_id: str, event_id: str) -> str:
    """Namespaced identity: ten sam event ID w dwóch kalendarzach nie koliduje."""

    calendar_id = (calendar_id or "").strip()
    event_id = (event_id or "").strip()
    if not calendar_id or not event_id:
        raise ValueError("calendar_id and event_id are required")
    namespace = hashlib.sha256(calendar_id.encode("utf-8")).hexdigest()[:16]
    return f"{namespace}:{event_id}"


def _normalize_name(value: str | None) -> str:
    value = (value or "").strip().casefold().replace("ł", "l")
    value = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _normalize_phone(value: str | None) -> str:
    digits = "".join(re.findall(r"\d", value or ""))
    if len(digits) == 11 and digits.startswith("48"):
        digits = digits[2:]
    return digits


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def _stable_issue_ref(source_type: str, identity: str) -> str:
    digest = hashlib.sha256(f"{source_type}\0{identity}".encode("utf-8")).hexdigest()
    return f"res_{digest[:20]}"


def _guest_name(summary: Any) -> str:
    if not isinstance(summary, str):
        return ""
    return _COMMON_SUMMARY_PREFIX_RE.sub("", summary).strip()


def _party_size(*values: Any) -> int | None:
    for value in values:
        if not isinstance(value, str):
            continue
        match = _PARTY_SIZE_RE.search(value)
        if match:
            parsed = int(match.group(1))
            return parsed if parsed > 0 else None
    return None


def _contact_details(value: Any) -> tuple[str | None, str | None]:
    """Czyta tylko jawnie etykietowane pola kontaktowe, nigdy całej notatki."""

    if not isinstance(value, str):
        return None, None
    phone_match = _PHONE_RE.search(value)
    email_match = _EMAIL_RE.search(value)
    phone = phone_match.group(1).strip() if phone_match else None
    email = email_match.group(1).strip().lower() if email_match else None
    return phone, email


def _description_has_residual(value: Any) -> bool:
    """Pozwala tylko na jawny boilerplate i kompletne, znane linie techniczne."""

    if value is None or value == "":
        return False
    if not isinstance(value, str):
        return True
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        normalized = " ".join(line.casefold().split()).rstrip(":")
        if normalized in _SAFE_DESCRIPTION_LINES:
            continue
        if line and all(char in "-_=*•· " for char in line):
            continue
        if (
            _PARTY_SIZE_RE.fullmatch(line)
            or _PHONE_RE.fullmatch(line)
            or _EMAIL_RE.fullmatch(line)
            or _EMPTY_NOTE_LINE_RE.fullmatch(line)
        ):
            continue
        return True
    return False


def _attach_unambiguous_timezone(value: datetime, tz: ZoneInfo) -> datetime:
    """Dołącza TZID, odrzucając godzinę podwójną lub nieistniejącą przy DST."""

    first = value.replace(tzinfo=tz, fold=0)
    second = value.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("ambiguous_or_nonexistent_local_time")
    return first


def _google_datetime(component: Any) -> datetime:
    if not isinstance(component, Mapping):
        raise ValueError("missing_datetime")
    raw = component.get("dateTime")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("all_day_or_missing_datetime")
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_datetime") from exc
    if parsed.tzinfo is None:
        tzid = component.get("timeZone")
        if not isinstance(tzid, str) or not tzid.strip():
            raise ValueError("ambiguous_timezone")
        try:
            parsed = _attach_unambiguous_timezone(parsed, ZoneInfo(tzid.strip()))
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown_timezone") from exc
    return parsed.astimezone(WARSAW)


def _issue_time_from_google(event: Mapping[str, Any]) -> datetime | None:
    try:
        return _google_datetime(event.get("start"))
    except (TypeError, ValueError):
        return None


def _valid_reservation(
    *,
    source_type: str,
    source_external_id: str,
    starts_at: datetime,
    ends_at: datetime,
    party_size: int | None,
    guest_name: str,
    phone: str | None = None,
    email: str | None = None,
) -> ExternalReservation:
    if ends_at.astimezone(UTC) <= starts_at.astimezone(UTC):
        raise ValueError("invalid_duration")
    if starts_at.utcoffset() != ends_at.utcoffset() or starts_at.fold or ends_at.fold:
        raise ValueError("unsupported_dst_transition")
    if starts_at.date() != ends_at.date():
        raise ValueError("unsupported_cross_day")
    if party_size is None or party_size <= 0:
        raise ValueError("missing_party_size")
    if not guest_name.strip():
        raise ValueError("missing_guest_name")
    return ExternalReservation(
        source_type=source_type,
        source_external_id=source_external_id,
        starts_at=starts_at,
        ends_at=ends_at,
        party_size=party_size,
        guest_name=guest_name.strip(),
        phone=phone,
        email=email,
    )


def normalize_google_events(
    events: Iterable[Mapping[str, Any]],
    *,
    calendar_id: str,
    range_start: datetime,
    range_end: datetime,
) -> NormalizedExternalBatch:
    """Normalizuje Google events; ``range_end`` jest zawsze granicą wyłączną."""

    if (
        range_start.tzinfo is None
        or range_end.tzinfo is None
        or range_end.astimezone(UTC) <= range_start.astimezone(UTC)
    ):
        raise ValueError("invalid reconciliation range")
    records: list[ExternalReservation] = []
    invalid: list[InvalidExternalReservation] = []
    received = 0
    for event in events:
        received += 1
        if not isinstance(event, Mapping):
            invalid.append(InvalidExternalReservation("google", "invalid_event"))
            continue
        event_id = event.get("id")
        external_id: str | None = None
        try:
            external_id = google_source_external_id(calendar_id, str(event_id or ""))
        except ValueError:
            pass
        occurs_at = _issue_time_from_google(event)
        issue_party_size = _party_size(event.get("description"), event.get("summary"))
        if occurs_at is not None and not (
            range_start.astimezone(UTC)
            <= occurs_at.astimezone(UTC)
            < range_end.astimezone(UTC)
        ):
            continue
        status = str(event.get("status") or "").strip().lower()
        if status != "confirmed":
            invalid.append(
                InvalidExternalReservation(
                    "google",
                    "cancelled" if status == "cancelled" else "unconfirmed_status",
                    occurs_at,
                    external_id,
                    issue_party_size,
                )
            )
            continue
        if external_id is None:
            invalid.append(
                InvalidExternalReservation(
                    "google", "missing_event_id", occurs_at, party_size=issue_party_size
                )
            )
            continue
        try:
            starts_at = _google_datetime(event.get("start"))
            ends_at = _google_datetime(event.get("end"))
            if _description_has_residual(event.get("description")):
                raise ValueError("unsupported_guest_notes")
            phone, email = _contact_details(event.get("description"))
            record = _valid_reservation(
                source_type="google",
                source_external_id=external_id,
                starts_at=starts_at,
                ends_at=ends_at,
                party_size=issue_party_size,
                guest_name=_guest_name(event.get("summary")),
                phone=phone,
                email=email,
            )
        except (TypeError, ValueError) as exc:
            invalid.append(
                InvalidExternalReservation(
                    "google",
                    _safe_value_error_code(exc),
                    occurs_at,
                    external_id,
                    issue_party_size,
                )
            )
            continue
        records.append(record)
    return NormalizedExternalBatch(
        source_type="google",
        records=tuple(records),
        invalid=tuple(invalid),
        received_count=received,
    )


def _safe_value_error_code(exc: BaseException) -> str:
    """Zwraca wyłącznie stały kod techniczny, nigdy treść zewnętrznego wpisu."""

    allowed = {
        "all_day_or_missing_datetime",
        "ambiguous_or_nonexistent_local_time",
        "ambiguous_timezone",
        "invalid_datetime",
        "invalid_duration",
        "missing_datetime",
        "missing_guest_name",
        "missing_party_size",
        "unknown_timezone",
        "unsupported_dst_transition",
        "unsupported_guest_notes",
        "unsupported_cross_day",
    }
    message = str(exc)
    return message if message in allowed else "invalid_event"


def _unfold_ical_lines(payload: str) -> list[str]:
    raw_lines = (payload or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw_lines:
        if line[:1] in {" ", "\t"} and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _ical_property(line: str) -> tuple[str, dict[str, str], str] | None:
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].strip().upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, param_value = part.split("=", 1)
            params[key.strip().upper()] = param_value.strip().strip('"')
    return name, params, value


def _ical_text(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            output.append("\n" if escaped in {"n", "N"} else escaped)
            index += 2
        else:
            output.append(value[index])
            index += 1
    return "".join(output)


def _ical_datetime(params: Mapping[str, str], raw: str) -> datetime:
    value = raw.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        raise ValueError("all_day_or_missing_datetime")

    if value.endswith("Z"):
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(WARSAW)
        except ValueError as exc:
            raise ValueError("invalid_datetime") from exc

    offset_match = re.fullmatch(r"(\d{8}T\d{6})([+-]\d{4})", value)
    if offset_match:
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%S%z").astimezone(WARSAW)
        except ValueError as exc:
            raise ValueError("invalid_datetime") from exc

    tzid = params.get("TZID")
    if not tzid:
        raise ValueError("ambiguous_timezone")
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
        zoned = _attach_unambiguous_timezone(parsed, ZoneInfo(tzid))
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown_timezone") from exc
    except ValueError as exc:
        if str(exc) == "ambiguous_or_nonexistent_local_time":
            raise
        raise ValueError("invalid_datetime") from exc
    return zoned.astimezone(WARSAW)


def _ical_identity(uid: str, recurrence: tuple[Mapping[str, str], str] | None) -> str:
    uid = uid.strip()
    if not uid or any(ord(char) < 32 for char in uid):
        raise ValueError("missing_uid")
    if recurrence is None:
        return uid
    recurrence_at = _ical_datetime(recurrence[0], recurrence[1])
    recurrence_key = recurrence_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{uid}#{recurrence_key}"


class IcalStructureError(ValueError):
    """Struktura pliku nie pozwala bezpiecznie ustalić kompletu wydarzeń."""


def _ical_events(payload: str) -> list[list[tuple[str, dict[str, str], str]]]:
    lines = [line for line in _unfold_ical_lines(payload) if line.strip()]
    if (
        len(lines) < 2
        or lines[0].strip().upper() != "BEGIN:VCALENDAR"
        or lines[-1].strip().upper() != "END:VCALENDAR"
    ):
        raise IcalStructureError("invalid_ical_structure")

    events: list[list[tuple[str, dict[str, str], str]]] = []
    components: list[str] = []
    current: list[tuple[str, dict[str, str], str]] | None = None
    for raw_line in lines:
        stripped = raw_line.strip()
        marker = stripped.upper()
        if marker.startswith("BEGIN:"):
            component = marker.split(":", 1)[1]
            if not component or (not components and component != "VCALENDAR"):
                raise IcalStructureError("invalid_ical_structure")
            if component == "VCALENDAR" and components:
                raise IcalStructureError("invalid_ical_structure")
            if component == "VEVENT":
                if components != ["VCALENDAR"] or current is not None:
                    raise IcalStructureError("invalid_ical_structure")
                current = []
            components.append(component)
            continue
        if marker.startswith("END:"):
            component = marker.split(":", 1)[1]
            if not components or components[-1] != component:
                raise IcalStructureError("invalid_ical_structure")
            if component == "VEVENT":
                if current is None:
                    raise IcalStructureError("invalid_ical_structure")
                events.append(current)
                current = None
            components.pop()
            continue
        if not components or ":" not in raw_line:
            raise IcalStructureError("invalid_ical_structure")
        if current is not None and components == ["VCALENDAR", "VEVENT"]:
            prop = _ical_property(raw_line)
            if prop is None:
                raise IcalStructureError("invalid_ical_structure")
            current.append(prop)

    if components or current is not None:
        raise IcalStructureError("invalid_ical_structure")
    return events


def normalize_ical_payload(
    payload: str,
    *,
    range_start: datetime,
    range_end: datetime,
) -> NormalizedExternalBatch:
    """Minimalny parser VEVENT dla UID/DTSTART/DTEND bez reguł cyklicznych."""

    if (
        range_start.tzinfo is None
        or range_end.tzinfo is None
        or range_end.astimezone(UTC) <= range_start.astimezone(UTC)
    ):
        raise ValueError("invalid reconciliation range")
    records: list[ExternalReservation] = []
    invalid: list[InvalidExternalReservation] = []
    try:
        events = _ical_events(payload)
    except IcalStructureError:
        return NormalizedExternalBatch(
            source_type="ical",
            source_status="error",
            source_error_code="invalid_ical_structure",
        )
    for properties in events:
        grouped: dict[str, list[tuple[dict[str, str], str]]] = {}
        for name, params, value in properties:
            grouped.setdefault(name, []).append((params, value))

        starts_at: datetime | None = None
        external_id: str | None = None
        issue_summary = _ical_text(grouped.get("SUMMARY", [({}, "")])[0][1])
        issue_description = _ical_text(grouped.get("DESCRIPTION", [({}, "")])[0][1])
        issue_party_size = _party_size(issue_description, issue_summary)
        start_values = grouped.get("DTSTART", [])
        if len(start_values) == 1:
            try:
                starts_at = _ical_datetime(*start_values[0])
            except ValueError:
                # Główna walidacja poniżej zapisze stały kod błędu.
                pass
        if starts_at is not None and not (
            range_start.astimezone(UTC)
            <= starts_at.astimezone(UTC)
            < range_end.astimezone(UTC)
        ):
            continue
        try:
            if any(grouped.get(name) for name in ("RRULE", "RDATE", "EXDATE")):
                raise ValueError("recurring_event")
            if len(grouped.get("UID", [])) != 1:
                raise ValueError("missing_uid")
            uid = grouped["UID"][0][1]
            recurrence_values = grouped.get("RECURRENCE-ID", [])
            if len(recurrence_values) > 1:
                raise ValueError("invalid_recurrence_id")
            recurrence = recurrence_values[0] if recurrence_values else None
            external_id = _ical_identity(uid, recurrence)
            if len(grouped.get("DTSTART", [])) != 1 or len(grouped.get("DTEND", [])) != 1:
                raise ValueError("missing_datetime")
            starts_at = _ical_datetime(*grouped["DTSTART"][0])
            ical_status = grouped.get("STATUS", [({}, "")])[0][1].strip().upper()
            if ical_status not in {"", "CONFIRMED"}:
                raise ValueError(
                    "cancelled" if ical_status == "CANCELLED" else "unconfirmed_status"
                )
            ends_at = _ical_datetime(*grouped["DTEND"][0])
            summary = issue_summary
            description = issue_description
            if _description_has_residual(description):
                raise ValueError("unsupported_guest_notes")
            phone, email = _contact_details(description)
            records.append(
                _valid_reservation(
                    source_type="ical",
                    source_external_id=external_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    party_size=_party_size(description, summary),
                    guest_name=_guest_name(summary),
                    phone=phone,
                    email=email,
                )
            )
        except (TypeError, ValueError) as exc:
            code = str(exc)
            if code not in {
                "ambiguous_or_nonexistent_local_time",
                "ambiguous_timezone",
                "cancelled",
                "invalid_datetime",
                "invalid_duration",
                "invalid_recurrence_id",
                "missing_datetime",
                "missing_guest_name",
                "missing_party_size",
                "missing_uid",
                "recurring_event",
                "unknown_timezone",
                "unconfirmed_status",
                "unsupported_dst_transition",
                "unsupported_guest_notes",
                "unsupported_cross_day",
            }:
                code = "invalid_event"
            invalid.append(
                InvalidExternalReservation(
                    "ical", code, starts_at, external_id, issue_party_size
                )
            )
    return NormalizedExternalBatch(
        source_type="ical",
        records=tuple(records),
        invalid=tuple(invalid),
        received_count=len(events),
    )


def _empty_counters() -> dict[str, int]:
    return {category: 0 for category in REPORT_CATEGORIES}


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("range boundaries must be timezone-aware")
    return value.astimezone(WARSAW)


def _bucket_for_datetime(value: datetime | None, cutover_date: date) -> str:
    # Brak daty w uszkodzonym wpisie traktujemy konserwatywnie jako przyszły.
    if value is None:
        return "future"
    return "historical" if value.astimezone(WARSAW).date() < cutover_date else "future"


def _termin_datetime(termin: models.Termin) -> datetime:
    return datetime.combine(termin.data, termin.godz_od or time.min, tzinfo=WARSAW)


def _termin_in_range(termin: models.Termin, start: datetime, end: datetime) -> bool:
    value = _termin_datetime(termin)
    return start.astimezone(UTC) <= value.astimezone(UTC) < end.astimezone(UTC)


def _fingerprint_external(record: ExternalReservation) -> tuple[Any, ...]:
    starts_at = record.starts_at.astimezone(WARSAW)
    return (
        starts_at.date(),
        starts_at.time().replace(tzinfo=None),
        record.party_size,
        _normalize_name(record.guest_name),
    )


def _fingerprint_termin(termin: models.Termin) -> tuple[Any, ...]:
    return (
        termin.data,
        termin.godz_od,
        termin.liczba_osob,
        _normalize_name(termin.nazwisko),
    )


def _changed_fields(termin: models.Termin, record: ExternalReservation) -> list[str]:
    starts_at = record.starts_at.astimezone(WARSAW)
    ends_at = record.ends_at.astimezone(WARSAW)
    checks = (
        ("data", termin.data == starts_at.date()),
        ("godz_od", termin.godz_od == starts_at.time().replace(tzinfo=None)),
        ("godz_do", termin.godz_do == ends_at.time().replace(tzinfo=None)),
        ("liczba_osob", termin.liczba_osob == record.party_size),
        ("nazwisko", _normalize_name(termin.nazwisko) == _normalize_name(record.guest_name)),
        ("status", termin.status == "potwierdzona"),
        ("rodzaj", termin.rodzaj == "stolik"),
    )
    changed = [field_name for field_name, matches in checks if not matches]
    if record.phone is not None and _normalize_phone(termin.telefon) != _normalize_phone(record.phone):
        changed.append("telefon")
    if record.email is not None and _normalize_email(termin.email) != _normalize_email(record.email):
        changed.append("email")
    return changed


def _query_canonical(
    db: Session,
    *,
    range_start: datetime,
    range_end: datetime,
) -> list[models.Termin]:
    inclusive_last_date = (range_end - timedelta(microseconds=1)).date()
    candidates = (
        db.query(models.Termin)
        .filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.data >= range_start.date(),
            models.Termin.data <= inclusive_last_date,
        )
        .order_by(models.Termin.id)
        .all()
    )
    return [item for item in candidates if _termin_in_range(item, range_start, range_end)]


def _deduplicate_external(
    batch: NormalizedExternalBatch,
) -> tuple[list[ExternalReservation], list[InvalidExternalReservation]]:
    records: list[ExternalReservation] = []
    invalid = list(batch.invalid)
    seen: set[str] = set()
    for record in batch.records:
        if record.source_type != batch.source_type or record.source_external_id in seen:
            invalid.append(
                InvalidExternalReservation(
                    batch.source_type,
                    "duplicate_identity" if record.source_external_id in seen else "wrong_source",
                    record.starts_at,
                    record.source_external_id,
                    record.party_size,
                )
            )
            continue
        seen.add(record.source_external_id)
        records.append(record)
    return records, invalid


def _query_exact_identities(
    db: Session,
    *,
    source_type: str,
    external_ids: set[str],
) -> dict[str, models.Termin]:
    """Szuka identity globalnie: data i rodzaj nie mogą ukryć konfliktu UNIQUE."""

    exact: dict[str, models.Termin] = {}
    ordered_ids = sorted(external_ids)
    for offset in range(0, len(ordered_ids), 400):
        chunk = ordered_ids[offset:offset + 400]
        rows = (
            db.query(models.Termin)
            .filter(
                models.Termin.source_type == source_type,
                models.Termin.source_external_id.in_(chunk),
            )
            .order_by(models.Termin.id)
            .all()
        )
        for termin in rows:
            exact.setdefault(termin.source_external_id, termin)
    return exact


def _issue(
    *,
    category: str,
    source_type: str,
    identity: str,
    bucket: str,
    occurs_at: datetime | None,
    party_size: int | None,
    termin: models.Termin | None = None,
    changed_fields: Sequence[str] = (),
    invalid_reason: str | None = None,
) -> dict[str, Any]:
    local = occurs_at.astimezone(WARSAW) if occurs_at is not None else None
    result: dict[str, Any] = {
        "ref": _stable_issue_ref(source_type, identity),
        "category": category,
        "bucket": bucket,
        "date": local.date().isoformat() if local is not None else None,
        "time": local.strftime("%H:%M") if local is not None else None,
        "party_size": party_size,
        "termin_id": termin.id if termin is not None else None,
        "changed_fields": list(changed_fields),
    }
    if invalid_reason is not None:
        result["invalid_reason"] = invalid_reason
    return result


def _classify(
    db: Session,
    *,
    batch: NormalizedExternalBatch,
    range_start: datetime,
    range_end: datetime,
    cutover_date: date,
) -> tuple[dict[str, dict[str, int]], list[ExternalReservation], list[dict[str, Any]]]:
    counters = {"historical": _empty_counters(), "future": _empty_counters()}
    records, invalid = _deduplicate_external(batch)
    source_type_col = getattr(models.Termin, "source_type", None)
    source_external_id_col = getattr(models.Termin, "source_external_id", None)
    if source_type_col is None or source_external_id_col is None:
        raise RuntimeError("Termin source identity migration is required")
    canonical = _query_canonical(db, range_start=range_start, range_end=range_end)
    incoming_ids = {record.source_external_id for record in records} | {
        item.source_external_id for item in invalid if item.source_external_id
    }
    exact = _query_exact_identities(
        db,
        source_type=batch.source_type,
        external_ids=incoming_ids,
    )

    fallback: dict[tuple[Any, ...], list[models.Termin]] = {}
    for termin in canonical:
        source_type = getattr(termin, "source_type", None)
        fallback.setdefault(_fingerprint_termin(termin), []).append(termin)
        if source_type != batch.source_type:
            bucket = _bucket_for_datetime(_termin_datetime(termin), cutover_date)
            counters[bucket]["canonical_only"] += 1

    missing: list[ExternalReservation] = []
    issues: list[dict[str, Any]] = []
    valid_external_ids: set[str] = set()
    for record in records:
        valid_external_ids.add(record.source_external_id)
        bucket = _bucket_for_datetime(record.starts_at, cutover_date)
        termin = exact.get(record.source_external_id)
        if termin is not None:
            changed_fields = _changed_fields(termin, record)
            if not changed_fields:
                counters[bucket]["matched"] += 1
            else:
                counters[bucket]["changed"] += 1
                issues.append(
                    _issue(
                        category="changed",
                        source_type=batch.source_type,
                        identity=record.source_external_id,
                        bucket=bucket,
                        occurs_at=record.starts_at,
                        party_size=record.party_size,
                        termin=termin,
                        changed_fields=changed_fields,
                    )
                )
        elif candidates := fallback.get(_fingerprint_external(record)):
            counters[bucket]["possible_duplicate"] += 1
            issues.append(
                _issue(
                    category="possible_duplicate",
                    source_type=batch.source_type,
                    identity=record.source_external_id,
                    bucket=bucket,
                    occurs_at=record.starts_at,
                    party_size=record.party_size,
                    termin=min(candidates, key=lambda item: item.id),
                )
            )
        else:
            counters[bucket]["missing_in_termin"] += 1
            missing.append(record)
            issues.append(
                _issue(
                    category="missing_in_termin",
                    source_type=batch.source_type,
                    identity=record.source_external_id,
                    bucket=bucket,
                    occurs_at=record.starts_at,
                    party_size=record.party_size,
                )
            )

    known_external_ids = valid_external_ids | {
        issue.source_external_id for issue in invalid if issue.source_external_id
    }
    if batch.source_status == "ok":
        for termin in canonical:
            if getattr(termin, "source_type", None) != batch.source_type:
                continue
            source_external_id = getattr(termin, "source_external_id", None)
            if source_external_id not in known_external_ids:
                occurs_at = _termin_datetime(termin)
                bucket = _bucket_for_datetime(occurs_at, cutover_date)
                counters[bucket]["source_missing"] += 1
                issues.append(
                    _issue(
                        category="source_missing",
                        source_type=batch.source_type,
                        identity=source_external_id or f"termin:{termin.id}",
                        bucket=bucket,
                        occurs_at=occurs_at,
                        party_size=termin.liczba_osob,
                        termin=termin,
                    )
                )

    for invalid_item in invalid:
        bucket = _bucket_for_datetime(invalid_item.occurs_at, cutover_date)
        counters[bucket]["invalid_external"] += 1
        invalid_identity = (
            f"invalid:{invalid_item.source_external_id}:{invalid_item.code}"
            if invalid_item.source_external_id
            else (
                f"invalid:{invalid_item.code}:{invalid_item.occurs_at!s}:"
                f"{invalid_item.party_size!s}"
            )
        )
        issues.append(
            _issue(
                category="invalid_external",
                source_type=batch.source_type,
                identity=invalid_identity,
                bucket=bucket,
                occurs_at=invalid_item.occurs_at,
                party_size=invalid_item.party_size,
                termin=exact.get(invalid_item.source_external_id or ""),
                invalid_reason=invalid_item.code,
            )
        )
    if batch.source_status == "error":
        counters["future"]["invalid_external"] += 1
        issues.append(
            _issue(
                category="invalid_external",
                source_type=batch.source_type,
                identity=f"source-error:{batch.source_error_code or 'source_error'}",
                bucket="future",
                occurs_at=None,
                party_size=None,
                invalid_reason="source_error",
            )
        )
    issues.sort(key=lambda item: (item["bucket"], item["category"], item["ref"]))
    return counters, missing, issues


def _report(
    *,
    batch: NormalizedExternalBatch,
    counters: dict[str, dict[str, int]],
    issues: list[dict[str, Any]],
    range_start: datetime,
    range_end: datetime,
    cutover_date: date,
    coverage_through: datetime | None,
    generated_at: datetime,
    applied: int,
    apply_requested: bool,
    apply_error_code: str | None = None,
) -> dict[str, Any]:
    unresolved = (
        "missing_in_termin",
        "changed",
        "possible_duplicate",
        "source_missing",
        "invalid_external",
    )
    cutover_at = datetime.combine(cutover_date, time.min, tzinfo=WARSAW)
    includes_cutover_and_future = (
        range_start.astimezone(UTC)
        <= cutover_at.astimezone(UTC)
        < range_end.astimezone(UTC)
    )
    coverage_is_future = (
        coverage_through is not None
        and coverage_through.astimezone(UTC) > generated_at.astimezone(UTC)
    )
    coverage_is_after_cutover = (
        coverage_through is not None
        and coverage_through.astimezone(UTC) > cutover_at.astimezone(UTC)
    )
    range_covers_through = (
        coverage_through is not None
        and range_end.astimezone(UTC) >= coverage_through.astimezone(UTC)
    )
    coverage_sufficient = (
        includes_cutover_and_future
        and coverage_is_future
        and coverage_is_after_cutover
        and range_covers_through
    )
    safe_to_cutover = (
        batch.source_status == "ok"
        and apply_error_code is None
        and coverage_sufficient
        and not any(
            counters["future"][category] for category in unresolved
        )
    )
    source: dict[str, Any] = {
        "type": batch.source_type,
        "status": batch.source_status,
        "received": batch.received_count,
        "valid": len(batch.records),
        "invalid": (
            counters["historical"]["invalid_external"]
            + counters["future"]["invalid_external"]
        ),
    }
    if batch.source_error_code:
        source["error_code"] = batch.source_error_code
    apply_result: dict[str, Any] = {
        "requested": apply_requested,
        "inserted": applied,
        "status": "error" if apply_error_code else "ok",
    }
    if apply_error_code:
        apply_result["error_code"] = apply_error_code
    return {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(UTC).isoformat(),
        "cutover_date": cutover_date.isoformat(),
        "range": {
            "start": range_start.isoformat(),
            "end": range_end.isoformat(),
            "end_exclusive": True,
        },
        "coverage": {
            "cutover_at": cutover_at.isoformat(),
            "through": coverage_through.isoformat() if coverage_through else None,
            "includes_cutover_and_future": includes_cutover_and_future,
            "through_is_after_generated_at": coverage_is_future,
            "through_is_after_cutover": coverage_is_after_cutover,
            "range_covers_through": range_covers_through,
            "sufficient": coverage_sufficient,
        },
        "source": source,
        "historical": counters["historical"],
        "future": counters["future"],
        "issues": issues,
        "apply": apply_result,
        "safe_to_cutover": safe_to_cutover,
    }


def reconcile_reservations(
    db: Session,
    *,
    batch: NormalizedExternalBatch,
    range_start: datetime,
    range_end: datetime,
    cutover_date: date,
    coverage_through: datetime | None = None,
    apply: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Porównuje źródło i opcjonalnie importuje czyste braki w jednej transakcji.

    Rozbieżne rekordy nigdy nie są nadpisywane, wpisy nieobecne w źródle nie są
    usuwane, a możliwe duplikaty wymagają ręcznego rozstrzygnięcia.
    """

    range_start = _local_datetime(range_start)
    range_end = _local_datetime(range_end)
    if range_end.astimezone(UTC) <= range_start.astimezone(UTC):
        raise ValueError("range_end must be after range_start")
    generated_at = generated_at or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    if coverage_through is not None:
        coverage_through = _local_datetime(coverage_through)

    counters, missing, issues = _classify(
        db,
        batch=batch,
        range_start=range_start,
        range_end=range_end,
        cutover_date=cutover_date,
    )
    applied = 0
    apply_error_code: str | None = None
    if apply and batch.source_status == "ok" and missing:
        created_at = generated_at.astimezone(UTC).replace(tzinfo=None)
        for record in missing:
            starts_at = record.starts_at.astimezone(WARSAW)
            ends_at = record.ends_at.astimezone(WARSAW)
            db.add(
                models.Termin(
                    data=starts_at.date(),
                    nazwisko=record.guest_name.strip(),
                    liczba_osob=record.party_size,
                    telefon=record.phone,
                    status="potwierdzona",
                    zadatek=0.0,
                    utworzono_at=created_at,
                    godz_od=starts_at.time().replace(tzinfo=None),
                    godz_do=ends_at.time().replace(tzinfo=None),
                    kanal=record.source_type,
                    rodzaj="stolik",
                    stolik_id=None,
                    email=record.email,
                    source_type=record.source_type,
                    source_external_id=record.source_external_id,
                )
            )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            apply_error_code = "source_identity_conflict"
        except Exception:
            db.rollback()
            raise
        else:
            applied = len(missing)
        counters, _, issues = _classify(
            db,
            batch=batch,
            range_start=range_start,
            range_end=range_end,
            cutover_date=cutover_date,
        )

    return _report(
        batch=batch,
        counters=counters,
        issues=issues,
        range_start=range_start,
        range_end=range_end,
        cutover_date=cutover_date,
        coverage_through=coverage_through,
        generated_at=generated_at,
        applied=applied,
        apply_requested=apply,
        apply_error_code=apply_error_code,
    )


def failed_source_batch(source_type: str, error: BaseException) -> NormalizedExternalBatch:
    """Buduje bezpieczny status błędu bez kopiowania komunikatu wyjątku do raportu."""

    return NormalizedExternalBatch(
        source_type=source_type,
        source_status="error",
        source_error_code=type(error).__name__,
    )
