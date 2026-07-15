"""R5a: hash-only public credentials, atomic holds, quotas and consent proof."""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import models
import reservation_service


BOOKING_DATE = date(2035, 7, 16)
NOW = datetime(2035, 7, 15, 12, 0)
SECRET = "r5a-test-secret-that-never-leaves-the-service"


def _tables(db, count=4):
    rows = [
        models.Stolik(nazwa=f"R5a-S{index}", pojemnosc=4, aktywny=True)
        for index in range(1, count + 1)
    ]
    db.add_all(rows)
    db.commit()
    return [row.id for row in rows]


def _termin(db, *, table_ids=None, start=time(18, 0), end=time(20, 0)):
    table_ids = table_ids or []
    row = models.Termin(
        data=BOOKING_DATE,
        nazwisko="R5a guest",
        liczba_osob=6,
        status="rezerwacja",
        zadatek=0,
        utworzono_at=NOW,
        godz_od=start,
        godz_do=end,
        kanal="online",
        rodzaj="stolik",
        stolik_id=table_ids[0] if table_ids else None,
        stoliki_dodatkowe=(table_ids[1:] or None),
    )
    db.add(row)
    db.flush()
    return row


def _create_hold(
    db,
    *,
    table_ids,
    raw_session="session-a",
    raw_ip="198.51.100.10",
    start=time(18, 0),
    end=time(20, 0),
    expires_at=None,
    key="hold-key",
    session_limit=2,
    ip_limit=10,
):
    return reservation_service.create_public_hold(
        db,
        data=BOOKING_DATE,
        start=start,
        end=end,
        table_ids=table_ids,
        party_size=6,
        buffer_min=30,
        expires_at=expires_at or (NOW + timedelta(minutes=10)),
        raw_session=raw_session,
        raw_ip=raw_ip,
        secret=SECRET,
        now=NOW,
        allocation_snapshot={
            "stoliki": table_ids,
            "combination_id": 17 if len(table_ids) > 1 else None,
            "plan_version_id": 5,
            "room_id": 2,
            "room_name": "Main",
            "reason": ["best-fit", "room-priority"],
        },
        session_limit=session_limit,
        ip_limit=ip_limit,
        idempotency_key=key,
    )


def test_public_quota_is_db_backed_hash_only_and_fixed_window(db):
    assert reservation_service.consume_public_quota(
        db, scope="availability", raw_client="203.0.113.8", secret=SECRET,
        now=NOW, limit=2, window_seconds=60,
    ) == 1
    assert reservation_service.consume_public_quota(
        db, scope="availability", raw_client="203.0.113.8", secret=SECRET,
        now=NOW + timedelta(seconds=5), limit=2, window_seconds=60,
    ) == 2
    with pytest.raises(reservation_service.ReservationError) as limited:
        reservation_service.consume_public_quota(
            db, scope="availability", raw_client="203.0.113.8", secret=SECRET,
            now=NOW + timedelta(seconds=10), limit=2, window_seconds=60,
        )
    assert (limited.value.status_code, limited.value.code) == (
        429, "PUBLIC_RATE_LIMITED",
    )
    row = db.query(models.RezerwacjaPublicznaKwota).one()
    assert row.client_hash != "203.0.113.8"
    assert len(row.client_hash) == 64

    # A new fixed window succeeds and cleanup removes the expired counter.
    assert reservation_service.consume_public_quota(
        db, scope="availability", raw_client="203.0.113.8", secret=SECRET,
        now=NOW + timedelta(minutes=1), limit=2, window_seconds=60,
    ) == 1
    assert db.query(models.RezerwacjaPublicznaKwota).count() == 1


def test_management_token_is_hash_only_idempotent_and_rotates_once(db):
    termin = _termin(db)
    issued = reservation_service.create_management_token(
        db,
        termin_id=termin.id,
        scopes=["read", "cancel"],
        secret=SECRET,
        now=NOW,
        idempotency_key="create-42",
    )
    replay = reservation_service.create_management_token(
        db,
        termin_id=termin.id,
        scopes=["cancel", "read"],
        secret=SECRET,
        now=NOW + timedelta(seconds=1),
        idempotency_key="create-42",
    )
    assert replay.replayed is True
    assert replay.raw_token == issued.raw_token
    assert issued.record.token_hash == reservation_service.hash_management_token(
        issued.raw_token, secret=SECRET,
    )
    assert issued.raw_token not in {
        value for (value,) in db.query(models.RezerwacjaTokenZarzadzania.token_hash)
    }

    successor = reservation_service.consume_and_rotate_management_token(
        db,
        issued.raw_token,
        operation="cancel",
        idempotency_key="cancel-42",
        payload={"reason": "guest-request"},
        secret=SECRET,
        now=NOW + timedelta(minutes=1),
    )
    retry = reservation_service.consume_and_rotate_management_token(
        db,
        issued.raw_token,
        operation="cancel",
        idempotency_key="cancel-42",
        payload={"reason": "guest-request"},
        secret=SECRET,
        now=NOW + timedelta(minutes=2),
    )
    assert retry.replayed is True
    assert retry.raw_token == successor.raw_token
    assert successor.raw_token != issued.raw_token

    with pytest.raises(reservation_service.ReservationError) as reused:
        reservation_service.consume_and_rotate_management_token(
            db,
            issued.raw_token,
            operation="cancel",
            idempotency_key="cancel-42",
            payload={"reason": "different"},
            secret=SECRET,
            now=NOW + timedelta(minutes=2),
        )
    assert reused.value.code == "MANAGEMENT_TOKEN_USED"

    reservation_service.consume_and_rotate_management_token(
        db,
        successor.raw_token,
        operation="cancel",
        idempotency_key="cancel-43",
        payload={"reason": "second-action"},
        secret=SECRET,
        now=NOW + timedelta(minutes=3),
    )
    with pytest.raises(reservation_service.ReservationError) as advanced:
        reservation_service.consume_and_rotate_management_token(
            db,
            issued.raw_token,
            operation="cancel",
            idempotency_key="cancel-42",
            payload={"reason": "guest-request"},
            secret=SECRET,
            now=NOW + timedelta(minutes=4),
        )
    assert advanced.value.code == "MANAGEMENT_TOKEN_SUCCESSOR_USED"


def test_public_hold_claims_all_tables_and_consumes_atomically(db):
    table_ids = _tables(db, 2)
    guards = reservation_service.begin_locked_write(db, [BOOKING_DATE])
    issued = _create_hold(db, table_ids=table_ids)
    replay = _create_hold(db, table_ids=table_ids)
    assert replay.replayed is True
    assert replay.raw_token == issued.raw_token
    assert issued.record.token_hash != issued.raw_token
    assert issued.record.allocation_snapshot == {
        "type": "combination",
        "stoliki": table_ids,
        "combination_id": 17,
        "room": {"id": 2, "name": "Main"},
        "plan_version_id": 5,
        "reason": ["best-fit", "room-priority"],
        "kombinacja_planu_id": 17,
        "wersja_planu_id": 5,
    }
    claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=issued.record.id,
    ).all()
    assert len(claims) == 2 * 150
    assert {claim.stolik_id for claim in claims} == set(table_ids)
    assert all(
        claim.termin_id is None
        and claim.waitlist_id is None
        and claim.expires_at == NOW + timedelta(minutes=10)
        for claim in claims
    )

    termin = _termin(db, table_ids=table_ids)
    consumed = reservation_service.consume_public_hold(
        db,
        issued.raw_token,
        raw_session="session-a",
        termin_id=termin.id,
        secret=SECRET,
        now=NOW + timedelta(minutes=1),
    )
    reservation_service.touch_days(guards)
    db.commit()
    assert consumed.state == "consumed"
    assert consumed.termin_id == termin.id
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=issued.record.id,
    ).count() == 0
    transferred = db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=termin.id,
    ).all()
    assert len(transferred) == 300
    assert all(
        claim.public_hold_id is None
        and claim.waitlist_id is None
        and claim.expires_at is None
        for claim in transferred
    )


def test_public_hold_limits_release_expiry_and_session_bound_idempotency(db):
    table_ids = _tables(db, 4)
    reservation_service.begin_locked_write(db, [BOOKING_DATE])
    first = _create_hold(db, table_ids=[table_ids[0]], key="same-key")
    second = _create_hold(
        db,
        table_ids=[table_ids[1]],
        start=time(20, 0),
        end=time(21, 0),
        key="second-key",
    )
    with pytest.raises(reservation_service.ReservationError) as session_limited:
        _create_hold(
            db,
            table_ids=[table_ids[2]],
            start=time(21, 0),
            end=time(22, 0),
            key="third-key",
        )
    assert session_limited.value.code == "PUBLIC_HOLD_SESSION_LIMIT"

    released = reservation_service.release_public_hold(
        db,
        first.raw_token,
        raw_session="session-a",
        secret=SECRET,
        now=NOW + timedelta(minutes=1),
    )
    assert released.state == "released"
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=first.record.id,
    ).count() == 0

    # Same Idempotency-Key in another session derives another credential.
    other_session = _create_hold(
        db,
        table_ids=[table_ids[2]],
        raw_session="session-b",
        raw_ip="198.51.100.11",
        start=time(21, 0),
        end=time(22, 0),
        key="same-key",
    )
    assert other_session.raw_token != first.raw_token

    with pytest.raises(reservation_service.ReservationError) as ip_limited:
        _create_hold(
            db,
            table_ids=[table_ids[3]],
            raw_session="session-c",
            raw_ip="198.51.100.11",
            start=time(22, 0),
            end=time(23, 0),
            key="ip-limit",
            ip_limit=1,
        )
    assert ip_limited.value.code == "PUBLIC_HOLD_IP_LIMIT"

    second.record.expires_at = NOW + timedelta(seconds=30)
    db.flush()
    assert reservation_service.expire_public_holds(
        db, NOW + timedelta(minutes=1),
    ) == 1
    assert second.record.state == "expired"
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=second.record.id,
    ).count() == 0


def test_public_consent_false_is_valid_sensitive_data_is_encrypted_and_owner_xor(db):
    termin = _termin(db)
    waitlist = models.ListaOczekujacych(
        data=BOOKING_DATE,
        nazwisko="Waitlist guest",
        status="oczekuje",
        utworzono_at=NOW,
        kanal="online",
    )
    db.add(waitlist)
    db.flush()
    ip_hash = reservation_service.hash_public_client(
        "203.0.113.9", secret=SECRET, purpose="consent-ip",
    )
    declined = models.RezerwacjaZgodaPubliczna(
        termin_id=termin.id,
        notice_version="privacy-2026-07",
        notice_ack_at=NOW,
        marketing=False,
        marketing_version="marketing-2026-07",
        marketing_at=NOW,
        sensitive=False,
        retention_until=NOW + timedelta(days=365),
        ip_hash=ip_hash,
        created_at=NOW,
    )
    sensitive_value = "ą💥" * 500  # 1000 znaków, ale >2048 B po Fernet/base64
    sensitive = models.RezerwacjaZgodaPubliczna(
        waitlist_id=waitlist.id,
        notice_version="privacy-2026-07",
        notice_ack_at=NOW,
        marketing=False,
        marketing_version="marketing-2026-07",
        marketing_at=NOW,
        sensitive=True,
        sensitive_version="health-2026-07",
        sensitive_at=NOW,
        sensitive_data=sensitive_value,
        retention_until=NOW + timedelta(days=365),
        ip_hash=ip_hash,
        created_at=NOW,
    )
    db.add_all([declined, sensitive])
    db.commit()
    raw = db.execute(text(
        "SELECT sensitive_data FROM rezerwacje_zgody_publiczne WHERE id=:id"
    ), {"id": sensitive.id}).scalar_one()
    assert declined.marketing is False
    assert sensitive.sensitive_data == sensitive_value
    assert raw != sensitive_value
    assert sensitive_value not in raw
    assert len(raw) > 2048

    invalid = models.RezerwacjaZgodaPubliczna(
        termin_id=termin.id,
        waitlist_id=waitlist.id,
        notice_version="privacy-2026-07",
        notice_ack_at=NOW,
        marketing=False,
        marketing_version="marketing-2026-07",
        marketing_at=NOW,
        sensitive=False,
        retention_until=NOW + timedelta(days=365),
        ip_hash=ip_hash,
        created_at=NOW,
    )
    db.add(invalid)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(models.RezerwacjaZgodaPubliczna).count() == 2


def test_r5a_config_retention_check_and_defaults(db):
    config = db.get(models.LokalConfig, 1)
    assert config.rezerwacje_widget_v2 is False
    assert config.rezerwacje_retencja_dni == 365
    config.rezerwacje_retencja_dni = 29
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
