"""R7.2: anonimowy odrzucony popyt, replay waitlisty i trwały lejek wizyty."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json

import factories
import main
import models
import reservation_access
import reservation_demand
from auth import create_access_token
from deps import get_lokal_config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _future_day(offset=30):
    return date.today() + timedelta(days=offset)


def _enable_online(db):
    config = get_lokal_config(db)
    config.rezerwacje_online = True
    config.rezerwacje_widget_v2 = True
    config.rezerwacje_rodo_kontakt = "rodo@lokalo.test"
    config.rezerwacje_rodo_adres = "ul. Testowa 1, Warszawa"
    db.commit()


def _public_headers(key):
    return {
        "X-Reservation-Session": "r72-public-session-00000001",
        "Idempotency-Key": key,
    }


def _public_waitlist_payload(payload):
    return {
        **payload,
        "email": payload.get("email") or (
            None if payload.get("telefon") else "waitlist-r72@example.test"
        ),
        "privacy_notice_acknowledged": True,
        "privacy_notice_version": main.PUBLIC_PRIVACY_NOTICE_VERSION,
        "marketing_consent": False,
        "marketing_consent_version": main.PUBLIC_MARKETING_CONSENT_VERSION,
        "sensitive_data_consent": False,
    }


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_empty_aggregate_uses_null_percentages_and_neutral_tracking_day(db):
    day = _future_day()

    payload = reservation_demand.aggregate_demand(db, start=day, end=day)

    assert payload["okres"] == {"od": str(day), "do": str(day), "dni": 1}
    assert payload["odrzucony_popyt"]["proby"] == 0
    assert payload["odrzucony_popyt"]["osoby"] == 0
    assert payload["waitlista"] == {
        "wpisy": 0,
        "zaoferowano": 0,
        "zaakceptowano": 0,
        "odbyte": 0,
        "zaoferowano_proc": None,
        "zaakceptowano_proc": None,
        "odbyte_proc": None,
        "mediana_do_oferty_min": None,
    }
    assert payload["jakosc_danych"] == {
        "sledzenie_od": None,
        "wpisy_bez_zdarzenia": 0,
        "historyczne_bez_przyczyny": 0,
        "zaakceptowane_bez_potwierdzonej_wizyty": 0,
    }


def test_public_rejected_demand_is_allowlisted_pii_free_and_idempotent(client, db):
    _enable_online(db)
    day = _future_day(31)
    endpoint = "/api/online/popyt/odrzucony"
    payload = {"data": str(day), "godz_od": "19:00", "liczba_osob": 4}
    headers = _public_headers("r72-demand-rejected-key-0001")

    first = client.post(endpoint, json=payload, headers=headers)
    replay = client.post(endpoint, json=payload, headers=headers)
    mismatch = client.post(
        endpoint,
        json={**payload, "liczba_osob": 5},
        headers=headers,
    )
    with_pii = client.post(
        endpoint,
        json={**payload, "nazwisko": "Nie wolno utrwalać"},
        headers=_public_headers("r72-demand-rejected-key-0002"),
    )
    future_subpath = client.post(
        f"{endpoint}/szczegoly",
        json=payload,
        headers=_public_headers("r72-demand-rejected-key-0003"),
    )

    assert first.status_code == 201, first.text
    assert first.json() == {"status": "zapisane", "replayed": False}
    assert replay.status_code == 201, replay.text
    assert replay.json() == {"status": "zapisane", "replayed": True}
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["code"] == "DEMAND_IDEMPOTENCY_KEY_REUSED"
    assert with_pii.status_code == 422
    assert future_subpath.status_code in {401, 403}

    db.expire_all()
    events = db.query(models.ReservationDemandEvent).all()
    assert len(events) == 1
    event = events[0]
    assert event.source_kind == "availability"
    assert event.channel == "online"
    assert event.reason_code == "service_closed"
    assert event.resource_kind == "policy"
    assert event.party_size == 4
    assert len(event.event_key_hash) == 64
    assert len(event.request_fingerprint) == 64
    raw = db.connection().exec_driver_sql(
        "SELECT * FROM reservation_demand_events"
    ).mappings().one()
    assert not ({"nazwisko", "telefon", "email", "notatka", "ip", "session"} & set(raw))
    assert "r72-public-session" not in json.dumps(dict(raw), default=str)


def test_public_demand_unique_race_replays_concurrent_winner(
    client, db, monkeypatch,
):
    _enable_online(db)
    day = _future_day(36)
    key = "r72-demand-concurrent-winner-0001"
    payload = {"data": str(day), "godz_od": "19:30", "liczba_osob": 3}
    original = reservation_demand.record_event
    injected = False

    def concurrent_winner(session, **kwargs):
        nonlocal injected
        if injected:
            return original(session, **kwargs)
        injected = True
        identity = kwargs["identity"]
        classification = kwargs["classification"]
        session.add(models.ReservationDemandEvent(
            source_kind=kwargs["source_kind"],
            channel=kwargs["channel"],
            requested_date=kwargs["requested_date"],
            requested_time=kwargs["requested_time"],
            party_size=kwargs["party_size"],
            reason_code=classification.reason_code,
            resource_kind=classification.resource_kind,
            event_key_hash=identity.key_hash,
            request_fingerprint=identity.request_fingerprint,
            captured_at=kwargs["captured_at"],
        ))
        session.commit()
        raise IntegrityError("concurrent demand insert", {}, Exception("unique"))

    monkeypatch.setattr(reservation_demand, "record_event", concurrent_winner)
    response = client.post(
        "/api/online/popyt/odrzucony",
        json=payload,
        headers=_public_headers(key),
    )

    assert response.status_code == 201, response.text
    assert response.json() == {"status": "zapisane", "replayed": True}
    db.expire_all()
    assert db.query(models.ReservationDemandEvent).count() == 1


def test_public_capture_rejects_client_claim_when_server_finds_availability(
    admin_client, client, db,
):
    day = _future_day(38)
    config = admin_client.put(
        "/api/lokal/config", json={"rezerwacje_online": True},
    )
    assert config.status_code == 200, config.text
    service = admin_client.post("/api/godziny-otwarcia", json={
        "nazwa": "Dostępny serwis R7.2",
        "dzien_tygodnia": day.weekday(),
        "godz_od": "12:00",
        "godz_do": "22:00",
        "ostatni_zasiadek": "21:00",
        "krok_slotu_min": 15,
        "domyslny_turn_time_min": 90,
    })
    assert service.status_code == 201, service.text
    table = admin_client.post(
        "/api/stoliki", json={"nazwa": "Wolny R7.2", "pojemnosc": 4},
    )
    assert table.status_code == 201, table.text
    client.headers.pop("Authorization", None)

    response = client.post(
        "/api/online/popyt/odrzucony",
        json={"data": str(day), "godz_od": "18:00", "liczba_osob": 2},
        headers=_public_headers("r72-false-demand-claim-0001"),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "DEMAND_AVAILABILITY_EXISTS"
    assert db.query(models.ReservationDemandEvent).count() == 0


def test_public_waitlist_replays_from_owner_and_rejects_key_reuse(client, db):
    _enable_online(db)
    day = _future_day(32)
    payload = _public_waitlist_payload({
        "data": str(day),
        "godz_od": "20:00",
        "liczba_osob": 6,
        "nazwisko": "Gość idempotentny",
    })
    headers = _public_headers("r72-waitlist-owner-key-0001")

    first = client.post(
        "/api/online/lista-oczekujacych", json=payload, headers=headers,
    )
    replay = client.post(
        "/api/online/lista-oczekujacych", json=payload, headers=headers,
    )
    mismatch = client.post(
        "/api/online/lista-oczekujacych",
        json={**payload, "nazwisko": "Inny gość"},
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert first.json()["replayed"] is False
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["wpis"] == first.json()["wpis"]
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["code"] == "WAITLIST_CREATE_KEY_REUSED"

    db.expire_all()
    owner = db.query(models.ListaOczekujacych).one()
    assert len(owner.create_key_hash) == 64
    assert len(owner.create_request_fingerprint) == 64
    assert owner.demand_reason_code == "service_closed"
    assert owner.demand_resource_kind == "policy"
    assert db.query(models.ReservationDemandEvent).count() == 1
    # Bez wcześniejszego capture availability bezpośredni POST waitlisty żyje
    # w lejku, ale nie fabrykuje odrzuconej próby ani jej podzbioru.
    aggregate = reservation_demand.aggregate_demand(db, start=day, end=day)
    assert aggregate["waitlista"]["wpisy"] == 1
    assert aggregate["odrzucony_popyt"]["proby"] == 0
    assert aggregate["odrzucony_popyt"]["z_waitlista"] == 0


def test_public_waitlist_unique_race_rolls_back_loser_pii(
    client, db, monkeypatch,
):
    _enable_online(db)
    day = _future_day(37)
    key = "r72-waitlist-concurrent-winner-0001"
    payload = _public_waitlist_payload({
        "data": str(day),
        "godz_od": "20:30",
        "liczba_osob": 5,
        "nazwisko": "Jedyny zwycięzca",
        "telefon": "500600701",
    })
    original_flush = Session.flush
    injected = False

    def concurrent_winner_flush(session, objects=None):
        nonlocal injected
        pending = next(
            (
                row for row in session.new
                if isinstance(row, models.ListaOczekujacych)
                and row.create_key_hash is not None
            ),
            None,
        )
        if injected or pending is None:
            return original_flush(session, objects)
        injected = True
        session.expunge(pending)
        winner = models.ListaOczekujacych(
            data=pending.data,
            godz_od=pending.godz_od,
            liczba_osob=pending.liczba_osob,
            nazwisko=pending.nazwisko,
            telefon=pending.telefon,
            email=pending.email,
            kanal_komunikacji=pending.kanal_komunikacji,
            status="oczekuje",
            kanal="online",
            utworzono_at=pending.utworzono_at,
            create_key_hash=pending.create_key_hash,
            create_request_fingerprint=pending.create_request_fingerprint,
            demand_reason_code=pending.demand_reason_code,
            demand_resource_kind=pending.demand_resource_kind,
        )
        safe_payload = {
            "data": pending.data,
            "godz_od": pending.godz_od,
            "liczba_osob": pending.liczba_osob,
            "kanal": "online",
        }
        event_identity = reservation_demand.event_identity(
            source_kind="waitlist",
            raw_key=key,
            payload=safe_payload,
            secret=main.SECRET_KEY,
        )
        session.add_all([
            winner,
            models.ReservationDemandEvent(
                source_kind="waitlist",
                channel="online",
                requested_date=pending.data,
                requested_time=pending.godz_od,
                party_size=pending.liczba_osob,
                reason_code=pending.demand_reason_code,
                resource_kind=pending.demand_resource_kind,
                event_key_hash=event_identity.key_hash,
                request_fingerprint=event_identity.request_fingerprint,
                captured_at=pending.utworzono_at,
            ),
        ])
        original_flush(session)
        session.commit()
        session.add(pending)
        raise IntegrityError("concurrent waitlist insert", {}, Exception("unique"))

    monkeypatch.setattr(Session, "flush", concurrent_winner_flush)
    response = client.post(
        "/api/online/lista-oczekujacych",
        json=payload,
        headers=_public_headers(key),
    )

    assert response.status_code == 201, response.text
    assert response.json()["replayed"] is True
    db.expire_all()
    owners = db.query(models.ListaOczekujacych).all()
    assert len(owners) == 1
    assert owners[0].nazwisko == payload["nazwisko"]
    assert owners[0].telefon == payload["telefon"]
    assert db.query(models.ReservationDemandEvent).count() == 1


def test_attendance_requires_completed_status_and_valid_measurement_then_survives_erasure(db):
    day = _future_day(33)
    seated = datetime(2026, 8, 20, 18, 0)
    termin = models.Termin(
        data=day,
        nazwisko="Gość wizyty",
        liczba_osob=2,
        status="potwierdzona",
        rodzaj="stolik",
        kanal="reczna",
        host_seated_at=seated,
        host_left_at=seated + timedelta(minutes=90),
    )
    db.add(termin)
    db.flush()
    waitlist = models.ListaOczekujacych(
        data=day,
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Gość wizyty",
        status="zaakceptowano",
        kanal="reczna",
        utworzono_at=seated - timedelta(minutes=30),
        zaoferowano_at=seated - timedelta(minutes=20),
        zaakceptowano_at=seated - timedelta(minutes=10),
        termin_id=termin.id,
        demand_reason_code="resource_occupied",
        demand_resource_kind="table_or_combination",
    )
    db.add(waitlist)
    db.flush()

    assert reservation_demand.mark_waitlist_attended(db, termin) == 0
    assert waitlist.attended_at is None
    termin.status = "odbyla"
    termin.host_left_at = seated - timedelta(minutes=1)
    assert reservation_demand.mark_waitlist_attended(db, termin) == 0
    termin.host_left_at = seated + timedelta(minutes=90)
    assert reservation_demand.mark_waitlist_attended(db, termin) == 1
    assert waitlist.attended_at == termin.host_left_at
    db.commit()

    # Późniejsze usunięcie pomiaru/owner PII nie może wymazać zwalidowanego faktu.
    termin.host_seated_at = None
    termin.host_left_at = None
    waitlist.nazwisko = "ZANONIMIZOWANO"
    db.commit()

    aggregate = reservation_demand.aggregate_demand(db, start=day, end=day)
    assert aggregate["waitlista"]["wpisy"] == 1
    assert aggregate["waitlista"]["odbyte"] == 1
    assert aggregate["waitlista"]["zaoferowano_proc"] == 100
    assert aggregate["waitlista"]["zaakceptowano_proc"] == 100
    assert aggregate["waitlista"]["odbyte_proc"] == 100


def test_rejected_aggregate_deduplicates_public_waitlist_and_excludes_available_operator(db):
    day = _future_day(39)
    captured = datetime(2026, 7, 19, 12, 0)
    db.add_all([
        # Publiczny zapis na waitlistę jest kontynuacją tej próby availability.
        models.ReservationDemandEvent(
            source_kind="availability",
            channel="online",
            requested_date=day,
            requested_time=time(18, 0),
            party_size=4,
            reason_code="resource_occupied",
            resource_kind="table_or_combination",
            event_key_hash="a" * 64,
            request_fingerprint="b" * 64,
            captured_at=captured,
        ),
        models.ReservationDemandEvent(
            source_kind="waitlist",
            channel="online",
            requested_date=day,
            requested_time=time(18, 0),
            party_size=4,
            reason_code="resource_occupied",
            resource_kind="table_or_combination",
            event_key_hash="c" * 64,
            request_fingerprint="d" * 64,
            captured_at=captured + timedelta(minutes=1),
        ),
        # Wewnętrzny wpis przy realnej odmowie jest samodzielną próbą.
        models.ReservationDemandEvent(
            source_kind="waitlist",
            channel="wewnetrzna",
            requested_date=day,
            requested_time=time(19, 0),
            party_size=3,
            reason_code="no_capacity_match",
            resource_kind="capacity",
            event_key_hash="e" * 64,
            request_fingerprint="f" * 64,
            captured_at=captured + timedelta(minutes=2),
        ),
        # Operator może dodać wpis mimo wolnego stolika, ale to nie jest odmowa.
        models.ReservationDemandEvent(
            source_kind="waitlist",
            channel="wewnetrzna",
            requested_date=day,
            requested_time=time(20, 0),
            party_size=6,
            reason_code="operator_decision",
            resource_kind="available",
            event_key_hash="1" * 64,
            request_fingerprint="2" * 64,
            captured_at=captured + timedelta(minutes=3),
        ),
        models.ListaOczekujacych(
            data=day,
            godz_od=time(18, 0),
            liczba_osob=4,
            nazwisko="Publiczna kontynuacja",
            status="oczekuje",
            kanal="online",
            utworzono_at=captured,
            demand_reason_code="resource_occupied",
            demand_resource_kind="table_or_combination",
        ),
        models.ListaOczekujacych(
            data=day,
            godz_od=time(19, 0),
            liczba_osob=3,
            nazwisko="Wewnętrzna odmowa",
            status="oczekuje",
            kanal="reczna",
            utworzono_at=captured,
            demand_reason_code="no_capacity_match",
            demand_resource_kind="capacity",
        ),
        models.ListaOczekujacych(
            data=day,
            godz_od=time(20, 0),
            liczba_osob=6,
            nazwisko="Decyzja operatora",
            status="oczekuje",
            kanal="reczna",
            utworzono_at=captured,
            demand_reason_code="operator_decision",
            demand_resource_kind="available",
        ),
    ])
    db.commit()

    payload = reservation_demand.aggregate_demand(db, start=day, end=day)

    rejected = payload["odrzucony_popyt"]
    assert rejected["proby"] == 2
    assert rejected["osoby"] == 7
    assert rejected["z_waitlista"] == 2
    assert rejected["z_waitlista"] <= rejected["proby"]
    assert {
        row["kod"]: (row["proby"], row["osoby"])
        for row in rejected["przyczyny"]
    } == {
        "resource_occupied": (1, 4),
        "no_capacity_match": (1, 3),
    }
    assert {row["kanal"]: row["proby"] for row in rejected["kanaly"]} == {
        "online": 1,
        "wewnetrzna": 1,
    }


def test_legacy_direct_acceptance_keeps_waitlist_funnel_monotonic(db):
    day = _future_day(40)
    captured = datetime(2026, 7, 19, 12, 0)
    db.add(models.ListaOczekujacych(
        data=day,
        godz_od=time(18, 0),
        liczba_osob=4,
        nazwisko="Legacy direct",
        status="zaakceptowano",
        kanal="reczna",
        utworzono_at=captured,
        zaakceptowano_at=captured + timedelta(minutes=5),
        demand_reason_code="legacy_unknown",
        demand_resource_kind="unknown",
    ))
    db.commit()

    waitlist = reservation_demand.aggregate_demand(
        db, start=day, end=day,
    )["waitlista"]

    assert waitlist["wpisy"] == 1
    assert waitlist["zaoferowano"] == 1
    assert waitlist["zaakceptowano"] == 1
    assert waitlist["zaoferowano_proc"] == 100
    assert waitlist["zaakceptowano_proc"] == 100
    assert waitlist["mediana_do_oferty_min"] is None


def test_orphan_waitlist_event_does_not_hide_legacy_owner_without_event(db):
    day = _future_day(41)
    captured = datetime(2026, 7, 19, 12, 0)
    db.add_all([
        models.ReservationDemandEvent(
            source_kind="waitlist",
            channel="wewnetrzna",
            requested_date=day,
            requested_time=time(18, 0),
            party_size=2,
            reason_code="resource_occupied",
            resource_kind="table_or_combination",
            event_key_hash="3" * 64,
            request_fingerprint="4" * 64,
            captured_at=captured,
        ),
        models.ListaOczekujacych(
            data=day,
            godz_od=time(19, 0),
            liczba_osob=5,
            nazwisko="Legacy bez eventu",
            status="oczekuje",
            kanal="reczna",
            utworzono_at=captured,
            demand_reason_code="legacy_unknown",
            demand_resource_kind="unknown",
        ),
    ])
    db.commit()

    quality = reservation_demand.aggregate_demand(
        db, start=day, end=day,
    )["jakosc_danych"]

    assert quality["wpisy_bez_zdarzenia"] == 1
    assert quality["historyczne_bez_przyczyny"] == 1


def test_waitlist_without_party_size_is_reported_as_missing_demand_event(db):
    day = _future_day(42)
    db.add(models.ListaOczekujacych(
        data=day,
        godz_od=time(18, 0),
        liczba_osob=None,
        nazwisko="Brak wielkości grupy",
        status="oczekuje",
        kanal="reczna",
        utworzono_at=datetime(2026, 7, 19, 12, 0),
        demand_reason_code="other",
        demand_resource_kind="unknown",
    ))
    db.commit()

    payload = reservation_demand.aggregate_demand(db, start=day, end=day)

    assert payload["odrzucony_popyt"]["z_waitlista"] == 0
    assert payload["jakosc_danych"]["wpisy_bez_zdarzenia"] == 1
    assert payload["jakosc_danych"]["historyczne_bez_przyczyny"] == 0


def test_analytics_contract_is_aggregate_only_and_has_exact_permission(admin_client, db):
    day = _future_day(34)
    captured = datetime(2026, 7, 19, 12, 0)
    db.add_all([
        models.ReservationDemandEvent(
            source_kind="availability",
            channel="online",
            requested_date=day,
            requested_time=time(19, 0),
            party_size=4,
            reason_code="resource_occupied",
            resource_kind="table_or_combination",
            event_key_hash="a" * 64,
            request_fingerprint="b" * 64,
            captured_at=captured,
        ),
        models.ReservationDemandEvent(
            source_kind="waitlist",
            channel="wewnetrzna",
            requested_date=day,
            requested_time=None,
            party_size=8,
            reason_code="operator_decision",
            resource_kind="available",
            event_key_hash="c" * 64,
            request_fingerprint="d" * 64,
            captured_at=captured + timedelta(minutes=1),
        ),
        models.ListaOczekujacych(
            data=day,
            liczba_osob=8,
            nazwisko="Dane nie mogą wyjść",
            telefon="500600700",
            email="pii@example.test",
            status="zaakceptowano",
            kanal="reczna",
            utworzono_at=captured,
            zaakceptowano_at=captured + timedelta(minutes=5),
            demand_reason_code="legacy_unknown",
            demand_resource_kind="unknown",
        ),
    ])
    db.commit()

    path = "/api/analityka/rezerwacje/popyt"
    response = admin_client.get(
        path, params={"start": str(day), "end": str(day)},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["odrzucony_popyt"]["proby"] == 1
    assert payload["odrzucony_popyt"]["osoby"] == 4
    assert payload["odrzucony_popyt"]["z_waitlista"] == 0
    assert payload["jakosc_danych"]["sledzenie_od"] == "2026-07-19"
    assert payload["jakosc_danych"]["historyczne_bez_przyczyny"] == 1
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "Dane nie mogą wyjść", "500600700", "pii@example.test",
        "event_id", "waitlist_id", "termin_id", "key_hash",
        "request_fingerprint", "actor_user", "login", "token", "session",
    ):
        assert forbidden not in serialized

    requirement = reservation_access.requirement_for("GET", path)
    assert requirement is not None
    assert requirement.all_of == ("rezerwacje.analityka",)
    assert reservation_access.requirement_for("POST", path).admin_only is True


def test_demand_analytics_http_auth_is_exact_and_future_subpath_stays_closed(client):
    day = _future_day(35)
    operations = factories.UserFactory(
        login="r72_operations_only",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.operacje": True},
    )
    analytics = factories.UserFactory(
        login="r72_analytics_exact",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.analityka": True},
    )
    path = "/api/analityka/rezerwacje/popyt"

    denied = client.get(
        path,
        params={"start": str(day), "end": str(day)},
        headers=_auth(operations),
    )
    allowed = client.get(
        path,
        params={"start": str(day), "end": str(day)},
        headers=_auth(analytics),
    )
    future_subpath = client.get(
        f"{path}/szczegoly",
        headers=_auth(analytics),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200, allowed.text
    assert future_subpath.status_code == 403
