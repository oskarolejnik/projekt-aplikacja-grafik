"""Skupiony kontrakt wspolnego evaluatora regul R3.

Testy nie uruchamiaja wyboru stolika. Sprawdzaja te same decyzje, ktore maja
zasilac widget, zapis reczny i symulator.
"""
from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

import models
import reservation_rules as rules
import reservation_service


MONDAY = date(2026, 8, 3)
NOW = datetime(2026, 8, 1, 10, 0, tzinfo=rules.WARSAW)


def _service(
    db,
    *,
    weekday: int = 0,
    start: time = time(18, 0),
    end: time = time(22, 0),
    step: int = 30,
    duration: int = 90,
    **values,
):
    row = models.GodzinyOtwarcia(
        dzien_tygodnia=weekday,
        godz_od=start,
        godz_do=end,
        ostatni_zasiadek=end,
        dlugosc_slotu_min=duration,
        aktywny=True,
        nazwa=values.pop("nazwa", "Kolacja"),
        **{
            key: value for key, value in values.items()
            if hasattr(models.GodzinyOtwarcia, key)
        },
    )
    # Pozwala uruchomic test rowniez przed dolaczeniem migracji modelu przez
    # rownolegly task. Po dodaniu kolumn sa to normalne atrybuty mapowane.
    row.krok_slotu_min = step
    row.domyslny_turn_time_min = duration
    for key, value in values.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def _request(
    *,
    booking_date: date = MONDAY,
    start: time = time(18, 0),
    people: int = 2,
    channel: str = "online",
    room_id: int | None = None,
    existing_id: int | None = None,
    end: time | None = None,
):
    return rules.RuleRequest(
        data=booking_date,
        godz_od=start,
        liczba_osob=people,
        kanal=channel,
        sala_id=room_id,
        existing_termin_id=existing_id,
        godz_do=end,
    )


def test_service_split_strict_lookup_slots_and_turn_time(db):
    service = _service(
        db,
        step=30,
        duration=90,
        turn_time_progi=[{"do_osob": 2, "min": 75}, {"do_osob": 8, "min": 120}],
    )

    assert rules.serwis_dla_godziny(db, MONDAY, time(17, 59), strict=True) is None
    assert rules.serwis_dla_godziny(db, MONDAY, time(17, 59), strict=False).id == service.id
    assert rules.krok_slotu(rules.serwis_dla_godziny(db, MONDAY, time(18, 0))) == 30
    assert rules.turn_time(rules.serwis_dla_godziny(db, MONDAY, time(18, 0)), 6) == 120
    assert [value.strftime("%H:%M") for value, _ in rules.sloty_dnia(db, MONDAY)][:3] == [
        "18:00", "18:30", "19:00",
    ]

    result = rules.evaluate_reservation_rules(
        db, _request(start=time(18, 30), people=2), now=NOW,
    )
    assert result.decision == "allow"
    assert result.krok_slotu_min == 30
    assert result.turn_time_min == 75
    assert result.godz_do == time(19, 45)
    assert result.to_dict()["resource_allocation"] == "not_simulated"


def test_online_requires_real_service_and_step_but_internal_legacy_is_permissive(db):
    online_without_service = rules.evaluate_reservation_rules(
        db, _request(booking_date=MONDAY, channel="online"), now=NOW,
    )
    assert [item.code for item in online_without_service.violations] == ["DATE_CLOSED"]

    internal_without_service = rules.evaluate_reservation_rules(
        db, _request(booking_date=MONDAY, channel="reczna"), now=NOW,
    )
    assert internal_without_service.decision == "allow"
    assert internal_without_service.turn_time_min == 120

    _service(db, step=30, duration=90)
    off_grid = rules.evaluate_reservation_rules(
        db, _request(start=time(18, 15), channel="online"), now=NOW,
    )
    assert [item.code for item in off_grid.violations] == ["SLOT_NOT_OFFERED"]
    error = rules.evaluation_to_reservation_error(off_grid)
    assert error.code == "SLOT_NOT_OFFERED"
    payload = error.availability.to_dict()
    assert payload["decision"] == "override_required"
    assert payload["violations"][0]["rule"] == "slot_step"
    assert payload["candidates"] == [] and payload["alternatives"] == []


def test_pacing_uses_service_anchored_half_open_buckets(db):
    _service(
        db,
        step=30,
        duration=60,
        pacing_okno_min=30,
        pacing_max_rez=2,
    )
    for index, start in enumerate((time(18, 5), time(18, 25)), start=1):
        termin = models.Termin(
            data=MONDAY,
            nazwisko=f"Gosc {index}",
            liczba_osob=2,
            status="potwierdzona",
            rodzaj="stolik",
            kanal="reczna",
            godz_od=start,
            godz_do=time(19, 25),
        )
        db.add(termin)
        db.flush()
        db.add(models.RezerwacjaPacingLedger(
            termin_id=termin.id,
            data=MONDAY,
            start_minute=start.hour * 60 + start.minute,
            covers=2,
            override=False,
            created_at=NOW.replace(tzinfo=None),
        ))
    db.flush()

    same_bucket = rules.evaluate_reservation_rules(
        db, _request(start=time(18, 29), channel="wewnetrzna"), now=NOW,
    )
    pacing = next(item for item in same_bucket.violations if item.code == "PACING_RESERVATION_LIMIT")
    assert (pacing.observed, pacing.limit, pacing.projected) == (2, 2, 3)

    next_bucket = rules.evaluate_reservation_rules(
        db, _request(start=time(18, 30), channel="wewnetrzna"), now=NOW,
    )
    assert "PACING_RESERVATION_LIMIT" not in {item.code for item in next_bucket.violations}


def test_minute_concurrent_usage_respects_global_room_channel_and_exclusion():
    rows = []
    for minute in range(1080, 1090):
        rows.extend((
            SimpleNamespace(termin_id=1, minute=minute, sala_id=1, kanal="online", covers=4),
            SimpleNamespace(termin_id=2, minute=minute, sala_id=1, kanal="reczna", covers=2),
            SimpleNamespace(termin_id=3, minute=minute, sala_id=2, kanal="online", covers=3),
        ))
    common = dict(
        rows=rows,
        start_minute=1085,
        end_minute=1095,
        channel="online",
        sala_id=1,
    )
    assert rules._concurrent_usage(**common, scope=rules._scope()) == (3, 9)
    assert rules._concurrent_usage(**common, scope=rules._scope(kanal="online")) == (2, 7)
    assert rules._concurrent_usage(**common, scope=rules._scope(sala_id=1)) == (2, 6)
    assert rules._concurrent_usage(
        **common, scope=rules._scope(sala_id=1, kanal="online"),
    ) == (1, 4)
    assert rules._concurrent_usage(
        **common, scope=rules._scope(), exclude_termin_id=1,
    ) == (2, 5)


def test_typed_override_more_specific_than_service_and_room(db, monkeypatch):
    service = _service(db, max_jednoczesnych_rez=10)
    room = models.SalaRezerwacyjna(
        nazwa="Sala R3", nazwa_klucz="sala-r3", aktywna=True, kolejnosc=0,
    )
    room.limit_jednoczesnych_rez = 5
    db.add(room)
    db.flush()
    overrides = [
        SimpleNamespace(
            id=1, serwis_id=service.id, sala_id=None, kanal="online",
            max_jednoczesnych_rez=4,
        ),
        SimpleNamespace(
            id=2, serwis_id=service.id, sala_id=room.id, kanal="online",
            max_jednoczesnych_rez=2,
        ),
    ]
    monkeypatch.setattr(rules, "_rule_rows", lambda _db: overrides)
    request = _request(room_id=room.id)
    resolved = rules._resolve_policy(
        db,
        request,
        rules.serwis_dla_godziny(db, MONDAY, time(18, 0)),
        room,
    )
    setting = resolved["concurrent_max_reservations"]
    assert setting.value == 2
    assert setting.scope == {
        "type": "room_channel", "sala_id": room.id, "kanal": "online",
    }
    assert setting.source == {"type": "override", "id": 2}


def test_calendar_exception_has_own_split_instead_of_first_service_inheritance(db):
    _service(db, start=time(12), end=time(15), step=60, duration=75, nazwa="Lunch")
    _service(db, start=time(18), end=time(23), step=30, duration=120, nazwa="Kolacja")
    exception = models.WyjatekKalendarza(
        data=MONDAY,
        typ="godziny_specjalne",
        godz_od=time(20),
        godz_do=time(23),
        ostatni_zasiadek=time(22),
        dlugosc_slotu_min=180,
        nazwa="Wieczor specjalny",
    )
    exception.krok_slotu_min = 15
    exception.domyslny_turn_time_min = 180
    db.add(exception)
    db.flush()

    services = rules.serwisy_dnia(db, MONDAY)
    assert len(services) == 1
    assert rules.krok_slotu(services[0]) == 15
    assert rules.turn_time(services[0], 4) == 180


@pytest.mark.parametrize("booking_date", [date(2026, 3, 29), date(2026, 10, 25)])
def test_warsaw_nonexistent_and_ambiguous_wall_time_are_stable_denials(db, booking_date):
    _service(
        db,
        weekday=6,
        start=time(0),
        end=time(5),
        step=30,
        duration=60,
    )
    result = rules.evaluate_reservation_rules(
        db,
        _request(booking_date=booking_date, start=time(2, 30)),
        now=datetime(2026, 1, 1, 12, 0, tzinfo=rules.WARSAW),
    )
    assert result.decision == "deny"
    assert result.code == "INVALID_LOCAL_TIME"
    assert result.violations[0].overrideable_by_operator is False


def test_enforce_allows_only_explicit_authorized_override(db):
    _service(db, step=30)
    result = rules.evaluate_reservation_rules(
        db, _request(start=time(18, 15)), now=NOW,
    )
    with pytest.raises(reservation_service.ReservationError) as forbidden:
        rules.enforce_rule_evaluation(result, override=True, can_override=False)
    assert forbidden.value.code == "OVERRIDE_FORBIDDEN"
    assert rules.enforce_rule_evaluation(
        result, override=True, can_override=True,
    ) is result


def test_same_day_past_slot_is_blocked_even_when_cutoff_is_zero(db):
    _service(
        db,
        weekday=NOW.date().weekday(),
        start=time(8),
        end=time(12),
        step=30,
        duration=60,
    )

    result = rules.evaluate_reservation_rules(
        db,
        _request(booking_date=NOW.date(), start=time(9), channel="online"),
        now=NOW,
    )

    assert result.decision == "override_required"
    violation = next(item for item in result.violations if item.rule == "cutoff")
    assert violation.code == "BOOKING_CUTOFF_REACHED"
    assert violation.limit == 0
    assert violation.observed == -60


def test_explicit_short_end_cannot_shorten_service_turn_time(db):
    _service(db, duration=90)

    result = rules.evaluate_reservation_rules(
        db,
        _request(start=time(18), end=time(18, 5), channel="wewnetrzna"),
        now=NOW,
    )

    assert result.decision == "allow"
    assert result.turn_time_min == 90
    assert result.godz_do == time(19, 30)


def test_explicit_blackout_warns_internal_operator_instead_of_legacy_allow(db):
    db.add(models.WyjatekKalendarza(data=MONDAY, typ="blackout"))
    db.flush()

    result = rules.evaluate_reservation_rules(
        db,
        _request(booking_date=MONDAY, channel="wewnetrzna"),
        now=NOW,
    )

    assert result.decision == "override_required"
    assert [item.code for item in result.violations] == ["DATE_CLOSED"]


def test_evaluator_rejects_second_precision_like_write_ledger(db):
    _service(db, duration=90)

    result = rules.evaluate_reservation_rules(
        db,
        _request(start=time(18, 0, 30), channel="wewnetrzna"),
        now=NOW,
    )

    assert result.decision == "deny"
    assert [item.code for item in result.violations] == [
        "INVALID_RESERVATION_INTERVAL",
    ]
    assert result.violations[0].overrideable_by_operator is False
