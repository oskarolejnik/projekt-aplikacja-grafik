"""Regression coverage for UTC hold lifecycles and local reservation slots."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

import database
import models
import reservation_service


SECRET = "clock-test-secret-not-for-production"


def _table(db, name: str) -> models.Stolik:
    table = models.Stolik(nazwa=name, pojemnosc=4, aktywny=True)
    db.add(table)
    db.flush()
    return table


def _waitlist(
    db,
    *,
    booking_date: date,
    name: str,
    table_id: int | None = None,
    expires_at: datetime | None = None,
) -> models.ListaOczekujacych:
    row = models.ListaOczekujacych(
        data=booking_date,
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko=name,
        status="oczekuje",
        utworzono_at=datetime(2035, 1, 1, 10, 0),
        kanal="reczna",
        hold_stolik_id=table_id,
        hold_godz_od=time(18, 0) if table_id is not None else None,
        hold_godz_do=time(19, 0) if table_id is not None else None,
        hold_bufor_min=0 if table_id is not None else None,
        hold_do=expires_at,
    )
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize(
    ("booking_date", "local_now", "expected_now_utc"),
    (
        (
            date(2035, 1, 16),
            datetime(2035, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
            datetime(2035, 1, 15, 11, 0),
        ),
        (
            date(2035, 7, 16),
            datetime(2035, 7, 15, 12, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
            datetime(2035, 7, 15, 10, 0),
        ),
    ),
    ids=("CET", "CEST"),
)
def test_public_and_waitlist_expiries_use_naive_utc_but_slots_stay_local(
    db,
    booking_date,
    local_now,
    expected_now_utc,
):
    waitlist_table = _table(db, "Clock waitlist")
    public_table = _table(db, "Clock public")
    waitlist = _waitlist(db, booking_date=booking_date, name="Clock guest")
    local_expiry = local_now + timedelta(minutes=15)
    expected_expiry_utc = expected_now_utc + timedelta(minutes=15)

    reservation_service.replace_waitlist_hold(
        db,
        waitlist_id=waitlist.id,
        table_ids=[waitlist_table.id],
        data=booking_date,
        expires_at=local_expiry,
        now=local_now,
        start=time(18, 0),
        end=time(19, 0),
    )
    issued = reservation_service.create_public_hold(
        db,
        data=booking_date,
        start=time(20, 0),
        end=time(21, 0),
        table_ids=[public_table.id],
        party_size=2,
        buffer_min=0,
        expires_at=local_expiry,
        raw_session="clock-session",
        raw_ip="192.0.2.10",
        secret=SECRET,
        now=local_now,
        allocation_snapshot={"stoliki": [public_table.id]},
        idempotency_key="clock-hold-key",
    )
    db.flush()

    waitlist_claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist.id,
    ).all()
    public_claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=issued.record.id,
    ).all()
    assert waitlist.hold_do == expected_expiry_utc
    assert issued.record.expires_at == expected_expiry_utc
    assert {claim.expires_at for claim in waitlist_claims} == {expected_expiry_utc}
    assert {claim.expires_at for claim in public_claims} == {expected_expiry_utc}
    assert {claim.minute for claim in waitlist_claims} == set(range(18 * 60, 19 * 60))
    assert {claim.minute for claim in public_claims} == set(range(20 * 60, 21 * 60))

    assert reservation_service.occupied_table_ids(
        db,
        data=booking_date,
        start=time(18, 0),
        end=time(21, 0),
        now=local_now + timedelta(minutes=14),
    ) == {waitlist_table.id, public_table.id}
    assert reservation_service.occupied_table_ids(
        db,
        data=booking_date,
        start=time(18, 0),
        end=time(21, 0),
        now=local_expiry,
    ) == set()


def test_public_hold_cleans_expired_waitlist_claim_before_unique_insert(db):
    now = datetime(2035, 7, 15, 10, 0)
    booking_date = date(2035, 7, 16)
    table = _table(db, "Expired waitlist slot")
    waitlist = _waitlist(
        db,
        booking_date=booking_date,
        name="Expired guest",
        table_id=table.id,
        expires_at=now - timedelta(seconds=1),
    )
    db.add(models.RezerwacjaStolikClaim(
        waitlist_id=waitlist.id,
        stolik_id=table.id,
        data=booking_date,
        minute=18 * 60,
        # The owner is authoritative. Cleanup must remove all of its claims even if
        # a historical bug left a mismatched, later claim expiry behind.
        expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(minutes=15),
    ))
    db.flush()

    issued = reservation_service.create_public_hold(
        db,
        data=booking_date,
        start=time(18, 0),
        end=time(19, 0),
        table_ids=[table.id],
        party_size=2,
        buffer_min=0,
        expires_at=now + timedelta(minutes=8),
        raw_session="fresh-session",
        raw_ip="192.0.2.20",
        secret=SECRET,
        now=now,
        allocation_snapshot={"stoliki": [table.id]},
        idempotency_key="fresh-after-expired-waitlist",
    )
    db.flush()

    assert waitlist.hold_stolik_id is None
    assert waitlist.hold_godz_od is None
    assert waitlist.hold_godz_do is None
    assert waitlist.hold_do is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist.id,
    ).count() == 0
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=issued.record.id,
    ).count() == 60


def test_startup_rebuild_drops_expired_waitlist_before_public_hold(
    db,
    monkeypatch,
):
    now = datetime(2035, 7, 15, 10, 0)
    booking_date = date(2035, 7, 16)
    table = _table(db, "Startup shared slot")
    waitlist = _waitlist(
        db,
        booking_date=booking_date,
        name="Startup expired",
        table_id=table.id,
        expires_at=now - timedelta(minutes=1),
    )
    public_hold = models.RezerwacjaPublicznyHold(
        token_hash="a" * 64,
        session_hash="b" * 64,
        ip_hash="c" * 64,
        state="active",
        data=booking_date,
        godz_od=time(18, 0),
        godz_do=time(19, 0),
        liczba_osob=2,
        stolik_id=table.id,
        allocation_snapshot={"stoliki": [table.id]},
        bufor_min=0,
        expires_at=now + timedelta(minutes=10),
        created_at=now - timedelta(minutes=1),
    )
    db.add(public_hold)
    db.flush()
    db.add(models.RezerwacjaStolikClaim(
        waitlist_id=waitlist.id,
        stolik_id=table.id,
        data=booking_date,
        minute=18 * 60,
        expires_at=now - timedelta(minutes=1),
        created_at=now - timedelta(minutes=20),
    ))
    db.commit()
    waitlist_id = waitlist.id
    public_hold_id = public_hold.id
    monkeypatch.setattr(reservation_service, "lifecycle_now_utc", lambda: now)

    database._rebuild_rezerwacje_ledger()
    db.expire_all()

    rebuilt_waitlist = db.get(models.ListaOczekujacych, waitlist_id)
    assert rebuilt_waitlist.hold_stolik_id is None
    assert rebuilt_waitlist.hold_godz_od is None
    assert rebuilt_waitlist.hold_godz_do is None
    assert rebuilt_waitlist.hold_do is None
    assert db.get(models.RezerwacjaPublicznyHold, public_hold_id).state == "active"
    claims = db.query(models.RezerwacjaStolikClaim).all()
    assert len(claims) == 60
    assert {claim.public_hold_id for claim in claims} == {public_hold_id}
    assert {claim.waitlist_id for claim in claims} == {None}
    assert {claim.expires_at for claim in claims} == {now + timedelta(minutes=10)}
