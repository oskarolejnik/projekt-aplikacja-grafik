"""R6a acceptance tests for server-side Reception/Host identity."""
from __future__ import annotations

from datetime import date, time, timedelta

from fastapi.testclient import TestClient
import pytest

import main
import models
import uprawnienia
import workstation_auth
import factories
from auth import create_access_token


PIN = "246802"


def _reception_user():
    return factories.UserFactory(
        login="recepcja_pin",
        rola="szef",
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )


def _register(admin_client, name="Recepcja główna"):
    response = admin_client.post(
        "/api/reservation-workstations",
        json={"name": name, "idle_timeout_seconds": 300},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _set_pin(admin_client, user, pin=PIN):
    response = admin_client.put(
        f"/api/users/{user.id}/reservation-pin",
        json={"pin": pin},
    )
    assert response.status_code == 204, response.text


def _drop_bearer(client):
    client.headers.pop("authorization", None)


def _unlock(client, user, pin=PIN):
    return client.post(
        "/api/reservation-workstations/unlock",
        json={"operator_id": user.id, "pin": pin},
        headers={"X-Lokalo-Workstation-Intent": "unlock"},
    )


def _csrf_headers(client):
    return {
        "X-Lokalo-Workstation-CSRF": client.cookies.get(
            workstation_auth.CSRF_COOKIE
        )
    }


def _authorization_header(client):
    return client.headers["authorization"]


def _restore_authorization(client, authorization):
    client.headers["authorization"] = authorization


def _assert_session_revoked(db, user, reason):
    db.expire_all()
    session = db.query(models.ReservationOperatorSession).filter_by(
        user_id=user.id,
    ).one()
    assert session.locked_at is not None
    assert session.lock_reason == reason
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        session_id=session.id,
        event="authz_revoke",
        outcome="success",
    ).count() == 1


def _cookie_header(response, name):
    prefix = f"{name}=".lower()
    return next(
        value for value in response.headers.get_list("set-cookie")
        if value.lower().startswith(prefix)
    )


def test_register_pin_unlock_and_manual_lock_are_server_side(admin_client, db):
    user = _reception_user()
    station = _register(admin_client)
    _set_pin(admin_client, user)

    users = admin_client.get("/api/users").json()
    configured = next(item for item in users if item["id"] == user.id)
    assert configured["reservation_pin_configured"] is True
    assert PIN not in str(configured)

    _drop_bearer(admin_client)
    gate = admin_client.get("/api/reservation-workstations/operators")
    assert gate.status_code == 200
    assert gate.headers["cache-control"] == "private, no-store"
    assert gate.json() == {
        "station": {
            "id": station["id"],
            "name": "Recepcja główna",
            "active": True,
            "idle_timeout_seconds": 300,
            "created_at": station["created_at"],
            "updated_at": station["updated_at"],
        },
        "operators": [{
            "id": user.id,
            "display_name": f"{user.pracownik.imie} {user.pracownik.nazwisko}",
            "last_used": False,
        }],
    }

    unlocked = _unlock(admin_client, user)
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["user"]["id"] == user.id
    assert unlocked.json()["idle_timeout_seconds"] == 300
    assert workstation_auth.SESSION_COOKIE in admin_client.cookies
    assert workstation_auth.CSRF_COOKIE in admin_client.cookies

    me = admin_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["login"] == user.login
    assert me.headers["cache-control"] == "private, no-store"
    assert {part.strip().casefold() for part in me.headers["vary"].split(",")} >= {
        "authorization", "cookie",
    }
    session = admin_client.get("/api/me/reservation-workstation")
    assert session.status_code == 200
    assert session.json()["active"] is True

    # PIN scope never becomes a general manager/admin session.
    assert admin_client.get("/api/users").status_code == 403

    locked = admin_client.post(
        "/api/me/reservation-workstation/lock",
        headers=_csrf_headers(admin_client),
    )
    assert locked.status_code == 204, locked.text
    after = admin_client.get("/api/auth/me")
    assert after.status_code == 423
    assert after.json()["detail"]["code"] == "WORKSTATION_LOCKED"

    stored_credential = db.get(models.ReservationOperatorCredential, user.id)
    stored_session = db.query(models.ReservationOperatorSession).one()
    assert stored_credential.pin_hash != PIN
    assert PIN not in stored_credential.pin_hash
    assert stored_session.token_hash != unlocked.cookies.get(
        workstation_auth.SESSION_COOKIE
    )
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="unlock", outcome="success", user_id=user.id,
    ).count() == 1
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="lock", outcome="success", user_id=user.id,
    ).count() == 1


def test_pin_failures_persist_and_escalate_for_operator_and_station(admin_client, db):
    user = _reception_user()
    station = _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)

    first = _unlock(admin_client, user, "000001")
    second = _unlock(admin_client, user, "000002")
    third = _unlock(admin_client, user, "000003")
    assert first.status_code == second.status_code == 401
    assert third.status_code == 429
    assert int(third.headers["retry-after"]) >= 29

    db.expire_all()
    credential = db.get(models.ReservationOperatorCredential, user.id)
    persisted_station = db.get(models.ReservationWorkstation, station["id"])
    assert credential.failed_attempts == 3
    assert credential.locked_until is not None
    assert persisted_station.failed_attempts == 3
    assert persisted_station.locked_until is not None
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="unlock", user_id=user.id,
    ).count() == 3

    # A correct PIN cannot bypass an active persisted lock.
    blocked = _unlock(admin_client, user, PIN)
    assert blocked.status_code == 429


def test_stolen_session_cookie_without_device_proof_is_rejected(admin_client):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    session_cookie = admin_client.cookies.get(workstation_auth.SESSION_COOKIE)
    csrf_cookie = admin_client.cookies.get(workstation_auth.CSRF_COOKIE)
    with TestClient(main.app) as stolen:
        stolen.cookies.set(workstation_auth.SESSION_COOKIE, session_cookie)
        stolen.cookies.set(workstation_auth.CSRF_COOKIE, csrf_cookie)
        response = stolen.get("/api/auth/me")
    assert response.status_code == 423
    assert response.json()["detail"]["reason"] == "device_mismatch"


def test_forget_device_cannot_lock_a_session_from_another_station(admin_client, db):
    user = _reception_user()
    first_station = _register(admin_client, "Recepcja A")
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200
    stolen_session = admin_client.cookies.get(workstation_auth.SESSION_COOKIE)

    admin = factories.UserFactory(login="admin_second_station", rola="admin", pracownik=None)
    from auth import create_access_token
    with TestClient(main.app) as second:
        second.headers["authorization"] = f"Bearer {create_access_token(admin)}"
        _register(second, "Recepcja B")
        _drop_bearer(second)
        second.cookies.set(workstation_auth.SESSION_COOKIE, stolen_session)
        response = second.post(
            "/api/reservation-workstations/forget-device",
            headers={"X-Lokalo-Workstation-Intent": "forget"},
        )
    assert response.status_code == 204, response.text

    db.expire_all()
    first_session = db.query(models.ReservationOperatorSession).filter_by(
        workstation_id=first_station["id"],
    ).one()
    assert first_session.locked_at is None


def test_pin_session_can_use_reservations_but_mutations_require_csrf(admin_client):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    reservations = admin_client.get(
        "/api/rezerwacje-stolik?start=2030-01-01&end=2030-01-02"
    )
    assert reservations.status_code == 200, reservations.text

    no_csrf = admin_client.post("/api/host/auto-no-show?data=2030-01-01")
    assert no_csrf.status_code == 403
    assert no_csrf.json()["detail"]["code"] == "WORKSTATION_CSRF_REJECTED"

    with_csrf = admin_client.post(
        "/api/host/auto-no-show?data=2030-01-01",
        headers=_csrf_headers(admin_client),
    )
    assert with_csrf.status_code == 200, with_csrf.text


def test_real_override_requires_one_use_reauth_grant_and_persists_only_hash(
    admin_client, db,
):
    booking_date = date.today() + timedelta(days=37)
    service = admin_client.post("/api/godziny-otwarcia", json={
        "nazwa": "Kolacja reauth",
        "dzien_tygodnia": booking_date.weekday(),
        "godz_od": "12:00",
        "godz_do": "22:00",
        "ostatni_zasiadek": "21:00",
        "krok_slotu_min": 15,
        "domyslny_turn_time_min": 90,
        "max_jednoczesnych_rez": 1,
    })
    assert service.status_code == 201, service.text
    tables = []
    for index in range(3):
        created = admin_client.post(
            "/api/stoliki",
            json={"nazwa": f"Reauth-{index + 1}", "pojemnosc": 4},
        )
        assert created.status_code == 201, created.text
        tables.append(created.json())

    base_payload = {
        "data": str(booking_date),
        "godz_od": "18:00",
        "liczba_osob": 2,
    }
    first = admin_client.post(
        "/api/rezerwacje-stolik",
        json={**base_payload, "stolik_id": tables[0]["id"], "nazwisko": "Pierwsza"},
    )
    assert first.status_code == 201, first.text

    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200
    csrf = _csrf_headers(admin_client)
    override = {
        "nadpisanie_limitow": {
            "powod": "walk_in",
            "notatka": "Recepcja potwierdziła przekroczenie limitu",
            "potwierdzone": True,
        },
    }
    second_payload = {
        **base_payload,
        "stolik_id": tables[1]["id"],
        "nazwisko": "Druga",
        **override,
    }

    missing = admin_client.post(
        "/api/rezerwacje-stolik", json=second_payload, headers=csrf,
    )
    assert missing.status_code == 428, missing.text
    assert missing.json()["code"] == "WORKSTATION_REAUTH_REQUIRED"
    assert db.query(models.Termin).filter_by(data=booking_date).count() == 1

    no_csrf = admin_client.post(
        "/api/me/reservation-workstation/reauthorize",
        json={"pin": PIN, "scope": "reservation_override"},
        headers={"X-Lokalo-Workstation-Intent": "reauthorize"},
    )
    assert no_csrf.status_code == 403, no_csrf.text
    assert no_csrf.json()["detail"]["code"] == "WORKSTATION_CSRF_REJECTED"
    no_intent = admin_client.post(
        "/api/me/reservation-workstation/reauthorize",
        json={"pin": PIN, "scope": "reservation_override"},
        headers=csrf,
    )
    assert no_intent.status_code == 403, no_intent.text

    wrong = admin_client.post(
        "/api/me/reservation-workstation/reauthorize",
        json={"pin": "000001", "scope": "reservation_override"},
        headers={
            **csrf,
            "X-Lokalo-Workstation-Intent": "reauthorize",
        },
    )
    assert wrong.status_code == 400, wrong.text
    assert wrong.json()["detail"]["code"] == "WORKSTATION_REAUTH_FAILED"
    assert admin_client.get("/api/auth/me").status_code == 200

    issued = admin_client.post(
        "/api/me/reservation-workstation/reauthorize",
        json={"pin": PIN, "scope": "reservation_override"},
        headers={
            **csrf,
            "X-Lokalo-Workstation-Intent": "reauthorize",
        },
    )
    assert issued.status_code == 200, issued.text
    raw_grant = issued.json()["grant"]
    assert raw_grant.startswith("wreauth_")
    assert raw_grant not in str(issued.cookies)

    db.expire_all()
    session = db.query(models.ReservationOperatorSession).one()
    assert session.reauth_grant_hash == workstation_auth.secret_hash(raw_grant)
    assert session.reauth_grant_hash != raw_grant
    assert session.reauth_scope == "reservation_override"
    assert session.reauth_expires_at > workstation_auth.utcnow_naive()
    assert session.reauth_expires_at <= (
        workstation_auth.utcnow_naive()
        + timedelta(seconds=workstation_auth.REAUTH_GRANT_SECONDS)
    )
    assert raw_grant not in str(
        [row.details for row in db.query(models.ReservationWorkstationAudit).all()]
    )

    authorized = admin_client.post(
        "/api/rezerwacje-stolik",
        json=second_payload,
        headers={**csrf, "X-Lokalo-Workstation-Reauth": raw_grant},
    )
    assert authorized.status_code == 201, authorized.text

    db.expire_all()
    session = db.query(models.ReservationOperatorSession).one()
    assert session.reauth_grant_hash is None
    assert session.reauth_scope is None
    assert session.reauth_expires_at is None
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="reauth", outcome="failure", user_id=user.id,
    ).count() == 1
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="reauth", outcome="success", user_id=user.id,
    ).count() == 1
    assert db.query(models.ReservationWorkstationAudit).filter_by(
        event="reauth_use", outcome="success", user_id=user.id,
    ).count() == 1

    reused = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            **base_payload,
            "stolik_id": tables[2]["id"],
            "nazwisko": "Trzecia",
            **override,
        },
        headers={**csrf, "X-Lokalo-Workstation-Reauth": raw_grant},
    )
    assert reused.status_code == 428, reused.text
    assert db.query(models.Termin).filter_by(data=booking_date).count() == 2


def test_permission_change_revokes_active_pin_session(admin_client):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    # Reuse the same browser, but ordinary admin JWT explicitly wins over cookies.
    admin = factories.UserFactory(login="admin_revoke_pin", rola="admin", pracownik=None)
    from auth import create_access_token
    admin_client.headers["authorization"] = f"Bearer {create_access_token(admin)}"
    changed = admin_client.put(
        f"/api/users/{user.id}/uprawnienia",
        json={"uprawnienia_override": {"rezerwacje.host": True}},
    )
    assert changed.status_code == 200, changed.text
    _drop_bearer(admin_client)

    response = admin_client.get("/api/auth/me")
    assert response.status_code == 423
    assert response.json()["detail"]["code"] == "WORKSTATION_LOCKED"


def test_idle_timeout_is_enforced_and_get_polling_does_not_extend_it(
    admin_client, db, monkeypatch,
):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    session = db.query(models.ReservationOperatorSession).one()
    session.last_seen_at = workstation_auth.utcnow_naive() - timedelta(seconds=301)
    db.commit()

    response = admin_client.get("/api/auth/me")
    assert response.status_code == 423
    assert response.json()["detail"]["reason"] == "idle"
    assert response.headers["cache-control"] == "private, no-store"


def test_explicit_idle_lock_is_audited_as_timeout_and_body_is_optional(admin_client, db):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    locked = admin_client.post(
        "/api/me/reservation-workstation/lock",
        json={"reason": "idle"},
        headers=_csrf_headers(admin_client),
    )
    assert locked.status_code == 204, locked.text

    db.expire_all()
    session = db.query(models.ReservationOperatorSession).one()
    assert session.lock_reason == "idle"
    audit = db.query(models.ReservationWorkstationAudit).filter_by(
        session_id=session.id,
        event="timeout",
    ).one()
    assert audit.details == {"reason": "idle"}


def test_user_deactivation_revokes_pin_session_before_stale_cookie_is_used(
    admin_client, db,
):
    authorization = _authorization_header(admin_client)
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    _restore_authorization(admin_client, authorization)
    changed = admin_client.put(
        f"/api/users/{user.id}",
        json={"aktywny": False},
    )
    assert changed.status_code == 200, changed.text
    _assert_session_revoked(db, user, "authorization_change")

    _drop_bearer(admin_client)
    stale = admin_client.get("/api/auth/me")
    assert stale.status_code == 423
    assert stale.json()["detail"]["code"] == "WORKSTATION_LOCKED"


def test_linked_employee_deactivation_revokes_pin_session_immediately(
    admin_client, db,
):
    authorization = _authorization_header(admin_client)
    user = _reception_user()
    employee = user.pracownik
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    _restore_authorization(admin_client, authorization)
    changed = admin_client.put(
        f"/api/pracownicy/{employee.id}",
        json={
            "imie": employee.imie,
            "nazwisko": employee.nazwisko,
            "aktywny": False,
            "kolor": employee.kolor,
            "dzial": employee.dzial or "obsluga",
            "kwalifikacje_ids": [],
            "stawki": [],
        },
    )
    assert changed.status_code == 200, changed.text
    _assert_session_revoked(db, user, "authorization_change")

    _drop_bearer(admin_client)
    assert admin_client.get("/api/auth/me").status_code == 423


@pytest.mark.parametrize(
    ("operation", "expected_reason"),
    (("change", "pin_changed"), ("revoke", "pin_revoked")),
)
def test_pin_change_or_revoke_immediately_revokes_existing_session(
    admin_client, db, operation, expected_reason,
):
    authorization = _authorization_header(admin_client)
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)
    assert _unlock(admin_client, user).status_code == 200

    _restore_authorization(admin_client, authorization)
    if operation == "change":
        changed = admin_client.put(
            f"/api/users/{user.id}/reservation-pin",
            json={"pin": "135790"},
        )
    else:
        changed = admin_client.delete(f"/api/users/{user.id}/reservation-pin")
    assert changed.status_code == 204, changed.text
    _assert_session_revoked(db, user, expected_reason)

    _drop_bearer(admin_client)
    assert admin_client.get("/api/auth/me").status_code == 423


def test_only_exact_active_reception_preset_is_pin_eligible(admin_client):
    station = _register(admin_client)
    valid = _reception_user()

    superset_override = dict(uprawnienia.override_dla_presetu(
        "szef", uprawnienia.PRESET_RECEPCJA_HOST,
    ))
    superset_override["rezerwacje.podglad"] = True
    candidates = [
        factories.UserFactory(login="pin_admin", rola="admin", pracownik=None),
        factories.UserFactory(login="pin_employee", rola="employee"),
        factories.UserFactory(
            login="pin_inactive",
            rola="szef",
            aktywny=False,
            uprawnienia_override=uprawnienia.override_dla_presetu(
                "szef", uprawnienia.PRESET_RECEPCJA_HOST,
            ),
        ),
        factories.UserFactory(
            login="pin_inactive_employee",
            rola="szef",
            pracownik=factories.PracownikFactory(aktywny=False),
            uprawnienia_override=uprawnienia.override_dla_presetu(
                "szef", uprawnienia.PRESET_RECEPCJA_HOST,
            ),
        ),
        factories.UserFactory(
            login="pin_superset",
            rola="szef",
            uprawnienia_override=superset_override,
        ),
    ]
    for candidate in candidates:
        rejected = admin_client.put(
            f"/api/users/{candidate.id}/reservation-pin",
            json={"pin": PIN},
        )
        assert rejected.status_code == 400, (candidate.login, rejected.text)

    _set_pin(admin_client, valid)
    changed = admin_client.put(
        f"/api/users/{valid.id}/uprawnienia",
        json={"uprawnienia_override": {"rezerwacje.podglad": True}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["preset"] is None

    _drop_bearer(admin_client)
    gate = admin_client.get("/api/reservation-workstations/operators")
    assert gate.status_code == 200, gate.text
    assert gate.json()["station"]["id"] == station["id"]
    assert valid.id not in {item["id"] for item in gate.json()["operators"]}


def test_explicit_bearer_wins_over_invalid_workstation_cookies(client):
    admin = factories.UserFactory(login="admin_bearer_priority", rola="admin", pracownik=None)
    client.headers["authorization"] = f"Bearer {create_access_token(admin)}"
    client.cookies.set(
        workstation_auth.DEVICE_COOKIE,
        "not-a-valid-device-proof",
        path="/api",
    )
    client.cookies.set(
        workstation_auth.SESSION_COOKIE,
        f"wst_{'x' * 48}",
        path="/api",
    )
    client.cookies.set(workstation_auth.CSRF_COOKIE, "wrong-csrf", path="/")

    response = client.post(
        "/api/reservation-workstations",
        json={"name": "Bearer ma pierwszeĹ„stwo", "idle_timeout_seconds": 300},
    )
    assert response.status_code == 201, response.text


def test_csrf_and_public_intent_contract_is_fail_closed(admin_client):
    user = _reception_user()
    _register(admin_client)
    _set_pin(admin_client, user)
    _drop_bearer(admin_client)

    no_unlock_intent = admin_client.post(
        "/api/reservation-workstations/unlock",
        json={"operator_id": user.id, "pin": PIN},
    )
    assert no_unlock_intent.status_code == 403
    assert no_unlock_intent.headers["cache-control"] == "private, no-store"

    assert _unlock(admin_client, user).status_code == 200
    csrf = admin_client.cookies.get(workstation_auth.CSRF_COOKIE)

    cookie_only = admin_client.post("/api/host/auto-no-show?data=2030-01-01")
    assert cookie_only.status_code == 403
    assert cookie_only.json()["detail"]["code"] == "WORKSTATION_CSRF_REJECTED"

    wrong_header = admin_client.post(
        "/api/host/auto-no-show?data=2030-01-01",
        headers={"X-Lokalo-Workstation-CSRF": "wrong"},
    )
    assert wrong_header.status_code == 403
    assert wrong_header.headers["cache-control"] == "private, no-store"
    assert {part.strip().casefold() for part in wrong_header.headers["vary"].split(",")} >= {
        "authorization", "cookie",
    }

    admin_client.cookies.delete(workstation_auth.CSRF_COOKIE)
    header_only = admin_client.post(
        "/api/host/auto-no-show?data=2030-01-01",
        headers={"X-Lokalo-Workstation-CSRF": csrf},
    )
    assert header_only.status_code == 403
    admin_client.cookies.set(workstation_auth.CSRF_COOKIE, csrf, path="/")

    no_forget_intent = admin_client.post(
        "/api/reservation-workstations/forget-device",
    )
    assert no_forget_intent.status_code == 403

    accepted = admin_client.post(
        "/api/host/auto-no-show?data=2030-01-01",
        headers={"X-Lokalo-Workstation-CSRF": csrf},
    )
    assert accepted.status_code == 200, accepted.text


def test_workstation_cookie_contract_is_scoped_strict_and_secure_in_production(
    admin, monkeypatch,
):
    import settings as app_settings

    monkeypatch.setattr(app_settings, "IS_DEV", False)
    user = _reception_user()
    with TestClient(main.app, base_url="https://testserver") as secure_client:
        secure_client.headers["authorization"] = f"Bearer {create_access_token(admin)}"
        registered = secure_client.post(
            "/api/reservation-workstations",
            json={"name": "Recepcja HTTPS", "idle_timeout_seconds": 300},
        )
        assert registered.status_code == 201, registered.text
        device_cookie = _cookie_header(registered, workstation_auth.DEVICE_COOKIE).lower()
        assert "httponly" in device_cookie
        assert "secure" in device_cookie
        assert "samesite=strict" in device_cookie
        assert "path=/api" in device_cookie
        assert "domain=" not in device_cookie

        _set_pin(secure_client, user)
        _drop_bearer(secure_client)
        unlocked = _unlock(secure_client, user)
        assert unlocked.status_code == 200, unlocked.text
        session_cookie = _cookie_header(unlocked, workstation_auth.SESSION_COOKIE).lower()
        csrf_cookie = _cookie_header(unlocked, workstation_auth.CSRF_COOKIE).lower()
        assert "httponly" in session_cookie
        assert "secure" in session_cookie
        assert "samesite=strict" in session_cookie
        assert "path=/api" in session_cookie
        assert "max-age=" not in session_cookie
        assert "domain=" not in session_cookie
        assert "httponly" not in csrf_cookie
        assert "secure" in csrf_cookie
        assert "samesite=strict" in csrf_cookie
        assert "path=/" in csrf_cookie
        assert "domain=" not in csrf_cookie


def test_named_operator_audit_survives_switch_and_old_session_cannot_mutate(
    admin_client, db,
):
    first = _reception_user()
    second = factories.UserFactory(
        login="recepcja_pin_druga",
        rola="szef",
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )
    _register(admin_client)
    _set_pin(admin_client, first)
    _set_pin(admin_client, second)
    reservation = models.Termin(
        data=date(2030, 1, 2),
        godz_od=time(18, 0),
        nazwisko="Audyt operatora",
        liczba_osob=2,
        rodzaj="stolik",
        status="rezerwacja",
        kanal="reczna",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    _drop_bearer(admin_client)
    assert _unlock(admin_client, first).status_code == 200
    first_device = admin_client.cookies.get(workstation_auth.DEVICE_COOKIE)
    first_session = admin_client.cookies.get(workstation_auth.SESSION_COOKIE)
    first_csrf = admin_client.cookies.get(workstation_auth.CSRF_COOKIE)
    arrived = admin_client.post(
        f"/api/host/rezerwacja/{reservation.id}/faza",
        json={"faza": "przybyl"},
        headers={"X-Lokalo-Workstation-CSRF": first_csrf},
    )
    assert arrived.status_code == 200, arrived.text

    switched = _unlock(admin_client, second)
    assert switched.status_code == 200, switched.text
    second_csrf = admin_client.cookies.get(workstation_auth.CSRF_COOKIE)

    with TestClient(main.app) as stale_client:
        stale_client.cookies.set(
            workstation_auth.DEVICE_COOKIE, first_device, path="/api",
        )
        stale_client.cookies.set(
            workstation_auth.SESSION_COOKIE, first_session, path="/api",
        )
        stale_client.cookies.set(
            workstation_auth.CSRF_COOKIE, first_csrf, path="/",
        )
        stale = stale_client.post(
            f"/api/host/rezerwacja/{reservation.id}/faza",
            json={"faza": "posadzony"},
            headers={"X-Lokalo-Workstation-CSRF": first_csrf},
        )
    assert stale.status_code == 423
    assert stale.json()["detail"]["reason"] == "switch"

    db.expire_all()
    assert db.get(models.Termin, reservation.id).faza_hosta == "przybyl"
    first_audit = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation.id,
        action="host",
    ).one()
    assert first_audit.actor_user_id == first.id
    assert first_audit.actor_login == first.login

    seated = admin_client.post(
        f"/api/host/rezerwacja/{reservation.id}/faza",
        json={"faza": "posadzony"},
        headers={"X-Lokalo-Workstation-CSRF": second_csrf},
    )
    assert seated.status_code == 200, seated.text
    db.expire_all()
    audits = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation.id,
        action="host",
    ).order_by(models.ReservationAudit.id).all()
    assert [(row.actor_user_id, row.actor_login) for row in audits] == [
        (first.id, first.login),
        (second.id, second.login),
    ]
