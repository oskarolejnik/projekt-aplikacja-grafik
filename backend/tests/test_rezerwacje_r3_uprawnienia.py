"""R3: uprawnienia do jawnego override i konfiguracji reguł dostępności."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import factories
import models
import uprawnienia
from auth import create_access_token


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _booking_date(days=21):
    return date.today() + timedelta(days=days)


def _service_with_concurrent_limit(admin_client, booking_date):
    response = admin_client.post("/api/godziny-otwarcia", json={
        "nazwa": "Kolacja R3",
        "dzien_tygodnia": booking_date.weekday(),
        "godz_od": "12:00",
        "godz_do": "22:00",
        "ostatni_zasiadek": "21:00",
        "krok_slotu_min": 15,
        "domyslny_turn_time_min": 90,
        "max_jednoczesnych_rez": 1,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _table(admin_client, name):
    response = admin_client.post(
        "/api/stoliki", json={"nazwa": name, "pojemnosc": 4},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reservation_payload(booking_date, table_id, name, **extra):
    return {
        "data": str(booking_date),
        "godz_od": "18:00",
        "stolik_id": table_id,
        "liczba_osob": 2,
        "nazwisko": name,
        **extra,
    }


def _manager():
    return factories.UserFactory(
        login="manager_r3",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.dane_kontaktowe": True,
            "rezerwacje.nadpisuj_limity": True,
        },
    )


def _reception():
    return factories.UserFactory(
        login="recepcja_r3",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )


@pytest.mark.parametrize(
    ("actor_factory", "reason_code"),
    [
        (_manager, "operational_decision"),
        (_reception, "walk_in"),
    ],
    ids=("manager", "recepcja-host"),
)
def test_manager_i_recepcja_nadpisuja_limit_po_ostrzezeniu_z_typed_powodem(
    admin_client, client, db, actor_factory, reason_code,
):
    booking_date = _booking_date()
    _service_with_concurrent_limit(admin_client, booking_date)
    first_table = _table(admin_client, "Limit R3-1")
    second_table = _table(admin_client, "Limit R3-2")
    first = admin_client.post(
        "/api/rezerwacje-stolik",
        json=_reservation_payload(
            booking_date, first_table["id"], "Pierwsza rezerwacja",
        ),
    )
    assert first.status_code == 201, first.text

    actor = actor_factory()
    headers = _headers(actor)
    payload = _reservation_payload(
        booking_date, second_table["id"], "Rezerwacja po ostrzeżeniu",
    )

    warning = client.post(
        "/api/rezerwacje-stolik", headers=headers, json=payload,
    )
    assert warning.status_code == 409, warning.text
    assert warning.json()["code"] == "CONCURRENT_RESERVATION_LIMIT"
    assert warning.json()["availability"]["decision"] == "override_required"
    assert warning.json()["availability"]["can_override"] is True

    missing_reason = client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={
            **payload,
            "nadpisanie_limitow": {"potwierdzone": True},
        },
    )
    assert missing_reason.status_code == 422
    not_confirmed = client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={
            **payload,
            "nadpisanie_limitow": {
                "powod": reason_code,
                "potwierdzone": False,
            },
        },
    )
    assert not_confirmed.status_code == 422
    other_without_note = client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={
            **payload,
            "nadpisanie_limitow": {
                "powod": "other",
                "potwierdzone": True,
            },
        },
    )
    assert other_without_note.status_code == 422

    note = f"Jawne potwierdzenie: {actor.login}"
    overridden = client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={
            **payload,
            "nadpisanie_limitow": {
                "powod": reason_code,
                "notatka": note,
                "potwierdzone": True,
            },
        },
    )
    assert overridden.status_code == 201, overridden.text

    db.expire_all()
    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=overridden.json()["id"], action="override",
    ).one()
    context = db.query(models.ReservationOverrideContext).filter_by(
        audit_id=audit.id,
    ).one()
    assert audit.actor_kind == "user"
    assert audit.actor_user_id == actor.id
    assert audit.actor_login == actor.login
    assert audit.reason == "capacity_override"
    assert context.audit_id == audit.id
    assert context.reason_code == reason_code
    assert context.note == note


def test_operator_bez_prawa_nie_moze_nadpisac_limitu(
    admin_client, client, db,
):
    booking_date = _booking_date(28)
    _service_with_concurrent_limit(admin_client, booking_date)
    first_table = _table(admin_client, "Bez prawa R3-1")
    second_table = _table(admin_client, "Bez prawa R3-2")
    first = admin_client.post(
        "/api/rezerwacje-stolik",
        json=_reservation_payload(booking_date, first_table["id"], "Pierwsza"),
    )
    assert first.status_code == 201, first.text

    operator = factories.UserFactory(
        login="operator_bez_override_r3",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.dane_kontaktowe": True,
        },
    )
    payload = _reservation_payload(
        booking_date, second_table["id"], "Próba bez prawa",
        nadpisanie_limitow={
            "powod": "operational_decision",
            "notatka": "Operator próbuje wymusić zapis",
            "potwierdzone": True,
        },
    )
    forbidden = client.post(
        "/api/rezerwacje-stolik", headers=_headers(operator), json=payload,
    )
    assert forbidden.status_code == 403
    assert "przekraczania limitów" in forbidden.json()["detail"]
    assert db.query(models.Termin).filter_by(
        data=booking_date, rodzaj="stolik",
    ).count() == 1
    assert db.query(models.ReservationAudit).filter_by(action="override").count() == 0
    assert db.query(models.ReservationOverrideContext).count() == 0


def test_uprawnienie_reguly_steruje_agregatem_symulatorem_i_konfiguracja(
    admin_client, client,
):
    booking_date = _booking_date(35)
    service = _service_with_concurrent_limit(admin_client, booking_date)
    room_response = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": "Sala reguł R3", "aktywna": True, "kolejnosc": 0},
    )
    assert room_response.status_code == 201, room_response.text
    room = room_response.json()

    rules_user = factories.UserFactory(
        login="konfigurator_regul_r3",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.reguly": True},
    )
    rules_headers = _headers(rules_user)
    reception = _reception()
    reception_headers = _headers(reception)

    assert client.get(
        "/api/rezerwacje/reguly", headers=rules_headers,
    ).status_code == 200
    # Recepcja może czytać ustawienia potrzebne do operacji, ale nie może ich zmieniać.
    assert client.get(
        "/api/rezerwacje/reguly", headers=reception_headers,
    ).status_code == 200

    simulation_payload = {
        "data": str(booking_date),
        "godz_od": "18:00",
        "liczba_osob": 2,
        "kanal": "wewnetrzna",
    }
    simulation = client.post(
        "/api/rezerwacje/reguly/symuluj",
        headers=rules_headers,
        json=simulation_payload,
    )
    assert simulation.status_code == 200, simulation.text
    reception_simulation = client.post(
        "/api/rezerwacje/reguly/symuluj",
        headers=reception_headers,
        json=simulation_payload,
    )
    assert reception_simulation.status_code == 200, reception_simulation.text
    assert reception_simulation.json()["decision"] in {
        "allow", "override_required", "deny",
    }

    policy_payload = {
        "okno_wyprzedzenia_dni": 120,
        "cutoff_min": 60,
        "min_grupa_online": 1,
        "max_grupa_online": 12,
        "bufor_min": 15,
    }
    policy = client.put(
        "/api/rezerwacje/reguly/polityka",
        headers=rules_headers,
        json=policy_payload,
    )
    assert policy.status_code == 200, policy.text
    assert policy.json() == policy_payload
    assert client.put(
        "/api/rezerwacje/reguly/polityka",
        headers=reception_headers,
        json=policy_payload,
    ).status_code == 403

    room_payload = {
        "online_aktywna": False,
        "wewnetrzna_aktywna": True,
        "limit_jednoczesnych_rez": 3,
        "limit_jednoczesnych_osob": 16,
        "domyslny_bufor_min": 20,
    }
    room_update = client.put(
        f"/api/rezerwacje/reguly/sale/{room['id']}",
        headers=rules_headers,
        json=room_payload,
    )
    assert room_update.status_code == 200, room_update.text
    assert {
        key: room_update.json()[key] for key in room_payload
    } == room_payload
    assert client.put(
        f"/api/rezerwacje/reguly/sale/{room['id']}",
        headers=reception_headers,
        json=room_payload,
    ).status_code == 403

    override_payload = {
        "serwis_id": service["id"],
        "sala_id": room["id"],
        "kanal": "wewnetrzna",
        "pacing_okno_min": 30,
        "pacing_max_rez": 2,
    }
    forbidden_create = client.post(
        "/api/nadpisania-regul-rezerwacji",
        headers=reception_headers,
        json=override_payload,
    )
    assert forbidden_create.status_code == 403

    created = client.post(
        "/api/nadpisania-regul-rezerwacji",
        headers=rules_headers,
        json=override_payload,
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    edited_payload = {
        **override_payload,
        "pacing_max_rez": 4,
        "max_jednoczesnych_osob": 24,
    }
    assert client.put(
        f"/api/nadpisania-regul-rezerwacji/{rule_id}",
        headers=reception_headers,
        json=edited_payload,
    ).status_code == 403
    edited = client.put(
        f"/api/nadpisania-regul-rezerwacji/{rule_id}",
        headers=rules_headers,
        json=edited_payload,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["pacing_max_rez"] == 4
    assert edited.json()["max_jednoczesnych_osob"] == 24

    assert client.delete(
        f"/api/nadpisania-regul-rezerwacji/{rule_id}",
        headers=reception_headers,
    ).status_code == 403
    assert client.delete(
        f"/api/nadpisania-regul-rezerwacji/{rule_id}",
        headers=rules_headers,
    ).status_code == 204


def test_uprawnienie_planu_sali_nie_pozwala_ominac_uprawnienia_regul(client):
    floor_user = factories.UserFactory(
        login="projektant_sali_bez_regul_r3",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.sala": True},
    )

    response = client.post(
        "/api/sale-rezerwacyjne",
        headers=_headers(floor_user),
        json={
            "nazwa": "Sala bez bocznego wejścia",
            "aktywna": True,
            "kolejnosc": 0,
            "online_aktywna": False,
            "wewnetrzna_aktywna": False,
            "limit_jednoczesnych_rez": 1,
            "limit_jednoczesnych_osob": 2,
            "domyslny_bufor_min": 60,
        },
    )

    assert response.status_code == 201, response.text
    room = response.json()
    assert room["online_aktywna"] is True
    assert room["wewnetrzna_aktywna"] is True
    assert room["limit_jednoczesnych_rez"] is None
    assert room["limit_jednoczesnych_osob"] is None
    assert room["domyslny_bufor_min"] is None
