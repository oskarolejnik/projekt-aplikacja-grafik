"""Regresje P0 R4: trwały bufor zasobu i konserwatywna zajętość live."""

from datetime import date, datetime, time

import pytest

import models
import reservation_service


BOOKING_DATE = date(2035, 7, 16)
NOW = datetime(2035, 7, 16, 17, 0)


def _tables(db, count=1):
    rows = [
        models.Stolik(nazwa=f"R4-S{index}", pojemnosc=4, aktywny=True)
        for index in range(1, count + 1)
    ]
    db.add_all(rows)
    db.commit()
    return [row.id for row in rows]


def _termin(db, *, table_ids, start, end, phase=None):
    row = models.Termin(
        data=BOOKING_DATE,
        nazwisko="Test R4",
        liczba_osob=2,
        status="potwierdzona",
        zadatek=0,
        utworzono_at=NOW,
        godz_od=start,
        godz_do=end,
        kanal="reczna",
        rodzaj="stolik",
        stolik_id=table_ids[0],
        stoliki_dodatkowe=(table_ids[1:] or None),
        faza_hosta=phase,
    )
    db.add(row)
    db.flush()
    return row


def _allocate(db, *, table_ids, start, end, buffer_min=0, phase=None):
    guards = reservation_service.begin_locked_write(db, [BOOKING_DATE])
    row = _termin(
        db,
        table_ids=table_ids,
        start=start,
        end=end,
        phase=phase,
    )
    reservation_service.replace_termin_allocation(
        db,
        termin_id=row.id,
        data=BOOKING_DATE,
        start=start,
        end=end,
        table_ids=table_ids,
        party_size=2,
        buffer_min=buffer_min,
        now=NOW,
    )
    reservation_service.touch_days(guards)
    db.commit()
    db.refresh(row)
    return row


@pytest.mark.parametrize(
    ("first_start", "first_end", "first_buffer", "second_start", "second_end", "second_buffer"),
    [
        (time(18, 0), time(20, 0), 30, time(20, 0), time(22, 0), 0),
        (time(20, 0), time(22, 0), 0, time(18, 0), time(20, 0), 30),
    ],
    ids=("buffer-owner-first", "buffer-owner-second"),
)
def test_post_visit_buffer_conflicts_in_both_creation_orders(
    db,
    first_start,
    first_end,
    first_buffer,
    second_start,
    second_end,
    second_buffer,
):
    table_id = _tables(db)[0]
    first = _allocate(
        db,
        table_ids=[table_id],
        start=first_start,
        end=first_end,
        buffer_min=first_buffer,
    )
    duration = (
        first_end.hour * 60 + first_end.minute
        - first_start.hour * 60 - first_start.minute
    )
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=first.id,
    ).count() == duration + first_buffer

    reservation_service.begin_locked_write(db, [BOOKING_DATE])
    candidate = _termin(
        db,
        table_ids=[table_id],
        start=second_start,
        end=second_end,
    )
    with pytest.raises(reservation_service.ReservationError) as conflict:
        reservation_service.replace_termin_allocation(
            db,
            termin_id=candidate.id,
            data=BOOKING_DATE,
            start=second_start,
            end=second_end,
            table_ids=[table_id],
            party_size=2,
            buffer_min=second_buffer,
            now=NOW,
        )
    db.rollback()

    assert conflict.value.code == "TABLE_CONFLICT"


def test_explicit_zero_buffer_is_not_replaced_by_global_fallback(db):
    config = db.get(models.LokalConfig, 1)
    config.rez_bufor_min = 30
    db.commit()
    table_id = _tables(db)[0]
    _allocate(
        db,
        table_ids=[table_id],
        start=time(18, 0),
        end=time(20, 0),
        buffer_min=0,
    )

    second = _allocate(
        db,
        table_ids=[table_id],
        start=time(20, 0),
        end=time(22, 0),
        buffer_min=0,
    )

    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=second.id,
    ).count() == 120


@pytest.mark.parametrize("phase", sorted(reservation_service.LIVE_HOST_PHASES))
def test_live_host_phase_blocks_all_component_tables_after_planned_end(db, phase):
    table_ids = _tables(db, count=2)
    live = _allocate(
        db,
        table_ids=table_ids,
        start=time(18, 0),
        end=time(20, 0),
        phase=phase,
    )

    occupied = reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=time(20, 0),
        end=time(22, 0),
        now=datetime(2035, 7, 16, 20, 1),
    )
    own_edit = reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=time(20, 0),
        end=time(22, 0),
        exclude_termin_id=live.id,
        now=datetime(2035, 7, 16, 20, 1),
    )

    assert occupied == set(table_ids)
    assert own_edit == set()


def test_left_and_released_reservation_does_not_block_tables(db):
    table_ids = _tables(db, count=2)
    live = _allocate(
        db,
        table_ids=table_ids,
        start=time(18, 0),
        end=time(20, 0),
        phase="posadzony",
    )

    guards = reservation_service.begin_locked_write(db, [BOOKING_DATE])
    live = db.get(models.Termin, live.id)
    live.faza_hosta = "wyszedl"
    live.status = "odbyla"
    reservation_service.release_termin_allocation(db, live.id)
    reservation_service.touch_days(guards)
    db.commit()

    assert reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=time(20, 0),
        end=time(22, 0),
        now=datetime(2035, 7, 16, 20, 1),
    ) == set()


def test_legacy_projection_without_materialized_buffer_uses_safe_fallback(db):
    config = db.query(models.LokalConfig).first()
    if config is None:
        config = models.LokalConfig()
        db.add(config)
    config.rez_bufor_min = 30
    table_id = _tables(db)[0]
    _termin(
        db,
        table_ids=[table_id],
        start=time(18, 0),
        end=time(20, 0),
    )
    db.commit()  # symuluje historyczny Termin bez rozszerzonych claimów R4

    assert reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=time(20, 0),
        end=time(22, 0),
        buffer_min=0,
        now=NOW,
    ) == {table_id}


@pytest.mark.parametrize(
    ("room_buffer", "rule_buffer", "expected_buffer"),
    [
        (45, None, 45),
        (15, 60, 60),
    ],
    ids=("room-buffer", "typed-rule-buffer"),
)
def test_legacy_projection_uses_largest_configured_r3_buffer(
    db,
    room_buffer,
    rule_buffer,
    expected_buffer,
):
    config = db.get(models.LokalConfig, 1)
    config.rez_bufor_min = 10
    room = models.SalaRezerwacyjna(
        nazwa=f"Bufor {expected_buffer}",
        nazwa_klucz=f"bufor-{expected_buffer}",
        aktywna=True,
        kolejnosc=0,
        domyslny_bufor_min=room_buffer,
    )
    db.add(room)
    db.flush()
    table = models.Stolik(
        nazwa=f"B-{expected_buffer}",
        pojemnosc=4,
        aktywny=True,
        sala_id=room.id,
        strefa=room.nazwa,
    )
    db.add(table)
    if rule_buffer is not None:
        db.add(models.RegulaDostepnosciRezerwacji(
            sala_id=room.id,
            kanal="oba",
            bufor_min=rule_buffer,
        ))
    db.flush()
    _termin(
        db,
        table_ids=[table.id],
        start=time(18, 0),
        end=time(20, 0),
    )
    db.commit()  # brak claimów symuluje przydział sprzed materializacji R4

    before_boundary = 20 * 60 + expected_buffer - 1
    boundary = 20 * 60 + expected_buffer

    def at(minute):
        return time(minute // 60, minute % 60)

    assert reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=at(before_boundary),
        end=at(before_boundary + 1),
        buffer_min=0,
        now=NOW,
    ) == {table.id}
    assert reservation_service.occupied_table_ids(
        db,
        data=BOOKING_DATE,
        start=at(boundary),
        end=at(boundary + 1),
        buffer_min=0,
        now=NOW,
    ) == set()
