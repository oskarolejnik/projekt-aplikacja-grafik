"""Kontrakt integracyjny R3: jeden evaluator dla symulatora i zapisów."""

from __future__ import annotations

from datetime import date, timedelta
import logging

import pytest
from sqlalchemy import text

import models
from public_widget_v2_helpers import enable_widget_v2, public_create_v2


def _day(days=7):
    return date.today() + timedelta(days=days)


def _service(admin_client, booking_date, **extra):
    payload = {
        "dzien_tygodnia": booking_date.weekday(),
        "godz_od": "12:00",
        "godz_do": "22:00",
        "ostatni_zasiadek": "21:00",
        "krok_slotu_min": 15,
        "domyslny_turn_time_min": 90,
        **extra,
    }
    response = admin_client.post("/api/godziny-otwarcia", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _table(admin_client, name, **extra):
    response = admin_client.post(
        "/api/stoliki",
        json={"nazwa": name, "pojemnosc": 4, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _manual(admin_client, booking_date, table_id, name, **extra):
    return admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": str(booking_date),
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 2,
            "nazwisko": name,
            **extra,
        },
    )


def test_split_slot_turn_time_i_strict_online(admin_client, client):
    booking_date = _day()
    _service(admin_client, booking_date)
    table = _table(admin_client, "R3-A")
    enable_widget_v2(admin_client)

    offered = public_create_v2(
        client,
        data=booking_date,
        godz_od="18:15",
        liczba_osob=2,
        nazwisko="Oferowany slot",
    )
    assert offered.status_code == 201, offered.text
    assert offered.json()["rezerwacja"]["godz_do"] == "19:45"

    not_offered = public_create_v2(
        client,
        data=booking_date,
        godz_od="18:07",
        liczba_osob=2,
        nazwisko="Nieistniejący slot",
    )
    assert not_offered.status_code == 409
    assert not_offered.json()["code"] == "SLOT_NOT_OFFERED"

    listed = admin_client.get("/api/godziny-otwarcia").json()["godziny"][0]
    assert listed["krok_slotu_min"] == 15
    assert listed["domyslny_turn_time_min"] == 90
    assert listed["dlugosc_slotu_min"] == 15
    assert table["id"]


def test_simulator_manual_i_audytowany_override_maja_ta_sama_decyzje(
    admin_client, db,
):
    booking_date = _day(14)
    _service(admin_client, booking_date, max_jednoczesnych_rez=1)
    first_table = _table(admin_client, "R3-B1")
    second_table = _table(admin_client, "R3-B2")

    first = _manual(admin_client, booking_date, first_table["id"], "Pierwsza")
    assert first.status_code == 201, first.text

    simulation = admin_client.post("/api/rezerwacje/reguly/symuluj", json={
        "data": str(booking_date),
        "godz_od": "18:00",
        "liczba_osob": 2,
        "kanal": "wewnetrzna",
    })
    assert simulation.status_code == 200, simulation.text
    assert simulation.json()["decision"] == "override_required"
    assert simulation.json()["code"] == "CONCURRENT_RESERVATION_LIMIT"
    assert simulation.json()["resource_allocation"] == "recommended"
    assert simulation.json()["allocation"]["state"] == "preview"
    assert simulation.json()["allocation"]["tables"]

    blocked = _manual(admin_client, booking_date, second_table["id"], "Druga")
    assert blocked.status_code == 409
    assert blocked.json()["code"] == simulation.json()["code"]

    overridden = _manual(
        admin_client,
        booking_date,
        second_table["id"],
        "Druga",
        nadpisanie_limitow={
            "powod": "operational_decision",
            "notatka": "Potwierdzono z managerem",
            "potwierdzone": True,
        },
    )
    assert overridden.status_code == 201, overridden.text
    reservation_id = overridden.json()["id"]

    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id, action="override",
    ).one()
    context = db.query(models.ReservationOverrideContext).filter_by(
        audit_id=audit.id,
    ).one()
    assert audit.reason == "capacity_override"
    assert audit.diff["override"]["violations"][0]["rule"] == "concurrent_reservations"
    assert context.reason_code == "operational_decision"
    assert context.note == "Potwierdzono z managerem"
    assert db.query(models.RezerwacjaOblozenieLedger).filter_by(
        termin_id=reservation_id, override=True,
    ).count() == 90

    raw_note = db.execute(text(
        "SELECT note FROM reservation_override_context WHERE id=:id"
    ), {"id": context.id}).scalar_one()
    assert raw_note != context.note


@pytest.mark.parametrize(
    ("endpoint", "base_payload", "expects_candidates", "idempotency_key"),
    [
        ("/api/rezerwacje-stolik/{rid}/auto-przydziel", {}, True, None),
        ("/api/host/rezerwacja/{rid}/przydziel-stolik", {"stolik_id": "target"}, False, None),
        ("/api/host/rezerwacja/{rid}/posadz", {"stolik_id": "target"}, False, None),
        (
            "/api/host/rezerwacja/{rid}/posadz",
            {"stoliki": ["target"], "oczekiwane_stoliki": []},
            False,
            "r6b3-seat-override",
        ),
    ],
    ids=("auto", "host-fixed", "host-seat", "host-seat-exact"),
)
def test_przydzial_hosta_respektuje_limit_i_pozwala_na_audytowany_override(
    admin_client, db, endpoint, base_payload, expects_candidates, idempotency_key,
):
    booking_date = _day(45)
    occupied = _table(admin_client, "R4 zajety")
    target = _table(admin_client, "R4 cel")
    first = _manual(admin_client, booking_date, occupied["id"], "Pierwsza")
    assert first.status_code == 201, first.text
    pending = admin_client.post("/api/rezerwacje-stolik", json={
        "data": str(booking_date),
        "godz_od": "18:00",
        "liczba_osob": 2,
        "nazwisko": "Do przydzielenia",
    })
    assert pending.status_code == 201, pending.text
    _service(admin_client, booking_date, max_jednoczesnych_rez=1)

    rid = pending.json()["id"]
    url = endpoint.format(rid=rid)
    payload = {
        key: (
            [target["id"]]
            if value == ["target"]
            else (target["id"] if value == "target" else value)
        )
        for key, value in base_payload.items()
    }
    headers = (
        {"Idempotency-Key": idempotency_key}
        if idempotency_key else None
    )
    warning = admin_client.post(url, json=payload, headers=headers)
    assert warning.status_code == 409, warning.text
    availability = warning.json()["availability"]
    assert availability["decision"] == "override_required"
    assert availability["can_override"] is True
    if expects_candidates:
        assert availability["candidates"]

    confirmed = admin_client.post(
        url,
        headers=headers,
        json={
            **payload,
            "nadpisanie_limitow": {
                "powod": "operational_decision",
                "notatka": "Host potwierdzil przekroczenie limitu",
                "potwierdzone": True,
            },
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    db.expire_all()
    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=rid, action="override",
    ).one()
    context = db.query(models.ReservationOverrideContext).filter_by(
        audit_id=audit.id,
    ).one()
    assert audit.reason == "capacity_override"
    assert context.reason_code == "operational_decision"
    assert db.query(models.RezerwacjaOblozenieLedger).filter_by(
        termin_id=rid, override=True,
    ).count() > 0


def test_reguly_crud_i_globalny_scope(admin_client):
    booking_date = _day(21)
    service = _service(admin_client, booking_date)

    created = admin_client.post("/api/nadpisania-regul-rezerwacji", json={
        "serwis_id": service["id"],
        "sala_id": None,
        "kanal": "online",
        "pacing_okno_min": 30,
        "pacing_max_rez": 3,
    })
    assert created.status_code == 201, created.text

    global_rule = admin_client.post("/api/nadpisania-regul-rezerwacji", json={
        "serwis_id": None,
        "sala_id": None,
        "kanal": "oba",
        "max_jednoczesnych_osob": 20,
    })
    assert global_rule.status_code == 201, global_rule.text

    aggregate = admin_client.get("/api/rezerwacje/reguly")
    assert aggregate.status_code == 200, aggregate.text
    assert {row["id"] for row in aggregate.json()["nadpisania"]} == {
        created.json()["id"], global_rule.json()["id"],
    }

    deleted = admin_client.delete(
        f"/api/nadpisania-regul-rezerwacji/{created.json()['id']}"
    )
    assert deleted.status_code == 204


def test_online_przechodzi_do_kolejnej_sali_po_limicie_pierwszej(
    admin_client, client, db,
):
    booking_date = _day(28)
    _service(admin_client, booking_date)
    first_room = models.SalaRezerwacyjna(
        nazwa="Pierwsza",
        nazwa_klucz="pierwsza",
        aktywna=True,
        kolejnosc=0,
        strategia_zapelniania="wypelniaj_kolejno",
        priorytet=0,
        online_aktywna=True,
        wewnetrzna_aktywna=True,
        limit_jednoczesnych_rez=1,
    )
    second_room = models.SalaRezerwacyjna(
        nazwa="Druga",
        nazwa_klucz="druga",
        aktywna=True,
        kolejnosc=1,
        strategia_zapelniania="wypelniaj_kolejno",
        priorytet=1,
        online_aktywna=True,
        wewnetrzna_aktywna=True,
        limit_jednoczesnych_rez=1,
    )
    db.add_all([first_room, second_room]); db.flush()
    first_table = models.Stolik(
        nazwa="P1", strefa=first_room.nazwa, sala_id=first_room.id,
        pojemnosc=4, aktywny=True, kolejnosc=0,
    )
    second_table = models.Stolik(
        nazwa="D1", strefa=second_room.nazwa, sala_id=second_room.id,
        pojemnosc=4, aktywny=True, kolejnosc=1,
    )
    db.add_all([first_table, second_table]); db.commit()
    enable_widget_v2(admin_client)

    def reserve(name):
        return public_create_v2(
            client,
            data=booking_date,
            godz_od="18:00",
            liczba_osob=2,
            nazwisko=name,
        )

    first = reserve("Najpierw pierwsza sala")
    second = reserve("Potem druga sala")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    db.expire_all()
    reservations = db.query(models.Termin).filter_by(
        data=booking_date, rodzaj="stolik",
    ).order_by(models.Termin.id).all()
    assert [row.stolik_id for row in reservations] == [first_table.id, second_table.id]


def test_shadow_compare_raportuje_roznice_bez_wplywu_na_wynik(
    admin_client, monkeypatch, caplog,
):
    import main

    booking_date = _day(35)
    _service(admin_client, booking_date)
    table = _table(admin_client, "R4-shadow")
    monkeypatch.setenv("RESERVATION_ALLOCATOR_SHADOW_COMPARE", "1")
    monkeypatch.setattr(main, "_wolne_przydzialy", lambda *args, **kwargs: [])

    with caplog.at_level(logging.WARNING, logger=main.logger.name):
        response = admin_client.post("/api/rezerwacje/reguly/symuluj", json={
            "data": str(booking_date),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "kanal": "wewnetrzna",
        })

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "allow"
    assert response.json()["allocation"]["tables"][0]["id"] == table["id"]
    record = next(
        item for item in caplog.records
        if item.getMessage() == "reservation_allocator_shadow_diff"
    )
    shadow = record.reservation_allocator_shadow
    assert shadow["canonical_decision"] == "allow"
    assert shadow["legacy_tables"] == ()
