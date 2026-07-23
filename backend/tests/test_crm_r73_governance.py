"""R7.3: controlled CRM export, data quality, reversible merges and consent facts."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
import io

import crm_governance
import factories
import main
import models
from sqlalchemy.exc import IntegrityError
from auth import create_access_token
from crm_identity import identity_hash, identity_key, reservation_fallback_hash


DAY = date(2026, 7, 23)


def _reservation(
    db,
    *,
    nazwisko: str,
    telefon: str | None,
    email: str | None,
    day_offset: int = 0,
    status: str = "odbyla",
    rodzaj: str = "stolik",
):
    row = models.Termin(
        rodzaj=rodzaj,
        data=DAY + timedelta(days=day_offset),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        nazwisko=nazwisko,
        telefon=telefon,
        email=email,
        liczba_osob=2,
        status=status,
        kanal="reczna",
        zadatek=0,
        utworzono_at=datetime(2026, 7, 1, 12, 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _profile(
    db,
    reservation,
    *,
    tags=None,
    note=None,
    legacy_marketing=False,
    key_hash=None,
):
    row = models.ProfilGoscia(
        klucz_hash=key_hash or identity_hash(reservation),
        nazwisko=reservation.nazwisko,
        tagi=tags,
        notatka=note,
        marketing_zgoda=legacy_marketing,
        utworzono_at=datetime(2026, 7, 1, 12, 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _exact_pair(db):
    """Different CRM identities with exact shared e-mail evidence."""
    source = _reservation(
        db,
        nazwisko="Anna Kowalska",
        telefon="600111222",
        email="wspolny@example.test",
    )
    target = _reservation(
        db,
        nazwisko="Anna K.",
        telefon="600333444",
        email="WSPOLNY@example.test",
        day_offset=1,
    )
    return source, target


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _manager(login: str, *permissions: str):
    return factories.UserFactory(
        login=login,
        rola="szef",
        pracownik=None,
        uprawnienia_override={permission: True for permission in permissions},
    )


def _create_merge(client, source, target, *, key="crm-merge-key-0001", expected=0):
    return client.post(
        "/api/crm/scalenia",
        headers={"Idempotency-Key": key},
        json={
            "source_ref": source.id,
            "target_ref": target.id,
            "expected_version": expected,
            "confirmed": True,
        },
    )


def _record_consent(
    client,
    reservation,
    decision,
    *,
    key,
    source="operator_in_person",
):
    return client.post(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
        headers={"Idempotency-Key": key},
        json={
            "decision": decision,
            "source": source,
            "document_version": main.PUBLIC_MARKETING_CONSENT_VERSION,
        },
    )


def test_quality_only_suggests_exact_contact_and_never_merges_automatically(
    admin_client,
    db,
):
    source, target = _exact_pair(db)
    fuzzy_left = _reservation(
        db,
        nazwisko="Jan Nowak",
        telefon="600555666",
        email="jan.one@example.test",
        day_offset=2,
    )
    fuzzy_right = _reservation(
        db,
        nazwisko="Jan Nowak",
        telefon="600777888",
        email="jan.two@example.test",
        day_offset=3,
    )

    response = admin_client.get("/api/crm/jakosc")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["podsumowanie"]["mozliwe_duplikaty"] == 1
    assert len(body["kandydaci"]) == 1
    candidate = body["kandydaci"][0]
    assert set(candidate["powod"]) == {"exact_email"}
    assert {candidate["source_ref"], candidate["target_ref"]} == {
        source.id,
        target.id,
    }
    assert "source_hash" not in candidate and "target_hash" not in candidate
    assert db.query(models.CrmGuestMerge).count() == 0

    exact_preview = admin_client.post(
        "/api/crm/scalenia/podglad",
        json={"source_ref": source.id, "target_ref": target.id},
    )
    assert exact_preview.status_code == 200, exact_preview.text
    assert exact_preview.json()["evidence"] == ["exact_email"]

    fuzzy_preview = admin_client.post(
        "/api/crm/scalenia/podglad",
        json={"source_ref": fuzzy_left.id, "target_ref": fuzzy_right.id},
    )
    assert fuzzy_preview.status_code == 409
    assert db.query(models.CrmGuestMerge).count() == 0


def test_contact_change_does_not_destructively_merge_profiles(admin_client, db):
    target = _reservation(
        db,
        nazwisko="Kontakt docelowy",
        telefon="600900800",
        email=None,
    )
    source = _reservation(
        db,
        nazwisko="Profil źródłowy",
        telefon=None,
        email=None,
        day_offset=1,
    )
    target_profile = _profile(db, target, tags=["docelowy"], note="Notatka docelowa")
    fallback_hash = reservation_fallback_hash(source.id)
    source_profile = _profile(
        db,
        source,
        tags=["zrodlo"],
        note="Notatka źródłowa",
        key_hash=fallback_hash,
    )

    response = admin_client.put(
        f"/api/rezerwacje-stolik/{source.id}",
        json={
            "data": str(source.data),
            "godz_od": "18:00",
            "godz_do": "20:00",
            "stolik_id": None,
            "liczba_osob": 2,
            "nazwisko": source.nazwisko,
            "telefon": "600900800",
            "email": None,
            "notatka": None,
            "zadatek": 0,
        },
    )

    # A conflicting contact correction may be accepted or rejected, but it must
    # never silently concatenate PII and delete the source profile.
    assert response.status_code in {200, 409}, response.text
    db.expire_all()
    assert db.get(models.ProfilGoscia, target_profile.id) is not None
    assert db.get(models.ProfilGoscia, source_profile.id) is not None
    assert db.get(models.ProfilGoscia, target_profile.id).notatka == "Notatka docelowa"
    assert db.get(models.ProfilGoscia, source_profile.id).notatka == "Notatka źródłowa"
    assert db.query(models.CrmGuestMerge).count() == 0


def test_merge_is_non_destructive_groups_history_and_undo_restores_it(
    admin_client,
    db,
):
    source, target = _exact_pair(db)
    source_profile = _profile(db, source, tags=["zrodlo"], note="Źródło")
    target_profile = _profile(db, target, tags=["cel"], note="Cel")

    created = _create_merge(admin_client, source, target)

    assert created.status_code == 201, created.text
    merge = created.json()
    assert merge["status"] == "active"
    assert merge["version"] == 1
    assert merge["replay"] is False
    db.expire_all()
    assert db.get(models.ProfilGoscia, source_profile.id) is not None
    assert db.get(models.ProfilGoscia, target_profile.id) is not None
    assert db.query(models.ProfilGoscia).count() == 2

    source_view = admin_client.get(
        f"/api/crm/rezerwacje/{source.id}/profil",
    )
    target_view = admin_client.get(
        f"/api/crm/rezerwacje/{target.id}/profil",
    )
    assert source_view.status_code == target_view.status_code == 200
    assert source_view.json()["historia_total"] == 2
    assert target_view.json()["historia_total"] == 2
    assert set(source_view.json()["profil"]["tagi"]) == {"zrodlo", "cel"}

    undone = admin_client.post(
        f"/api/crm/scalenia/{merge['id']}/cofnij",
        headers={"Idempotency-Key": "crm-merge-undo-0001"},
        json={"expected_version": 1},
    )

    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "reverted"
    assert undone.json()["version"] == 2
    assert undone.json()["replay"] is False
    assert admin_client.get(
        f"/api/crm/rezerwacje/{source.id}/profil",
    ).json()["historia_total"] == 1
    assert admin_client.get(
        f"/api/crm/rezerwacje/{target.id}/profil",
    ).json()["historia_total"] == 1
    assert db.query(models.ProfilGoscia).count() == 2


def test_merge_and_undo_are_idempotent_and_reject_stale_or_reused_keys(
    admin_client,
    db,
):
    source, target = _exact_pair(db)

    stale = _create_merge(
        admin_client,
        source,
        target,
        key="crm-merge-stale-0001",
        expected=1,
    )
    assert stale.status_code == 409
    assert db.query(models.CrmGuestMerge).count() == 0

    first = _create_merge(
        admin_client,
        source,
        target,
        key="crm-merge-replay-0001",
    )
    replay = _create_merge(
        admin_client,
        source,
        target,
        key="crm-merge-replay-0001",
    )
    mismatch = _create_merge(
        admin_client,
        target,
        source,
        key="crm-merge-replay-0001",
    )

    assert first.status_code == replay.status_code == 201
    assert first.json()["replay"] is False
    assert replay.json()["replay"] is True
    assert mismatch.status_code == 409
    assert db.query(models.CrmGuestMerge).count() == 1

    merge_id = first.json()["id"]
    undo_first = admin_client.post(
        f"/api/crm/scalenia/{merge_id}/cofnij",
        headers={"Idempotency-Key": "crm-undo-replay-0001"},
        json={"expected_version": 1},
    )
    undo_replay = admin_client.post(
        f"/api/crm/scalenia/{merge_id}/cofnij",
        headers={"Idempotency-Key": "crm-undo-replay-0001"},
        json={"expected_version": 1},
    )
    stale_undo = admin_client.post(
        f"/api/crm/scalenia/{merge_id}/cofnij",
        headers={"Idempotency-Key": "crm-undo-stale-0002"},
        json={"expected_version": 1},
    )

    assert undo_first.status_code == undo_replay.status_code == 200
    assert undo_first.json()["replay"] is False
    assert undo_replay.json()["replay"] is True
    assert stale_undo.status_code == 409
    row = db.get(models.CrmGuestMerge, merge_id)
    db.refresh(row)
    assert row.status == "reverted" and row.version == 2


def test_csv_export_neutralizes_formulas_and_commits_pii_free_audit(
    admin_client,
    db,
):
    _reservation(
        db,
        nazwisko="=2+2",
        telefon="+48600111222",
        email="@polecenie.example",
    )

    response = admin_client.post(
        "/api/crm/eksport",
        json={
            "columns": ["nazwisko", "telefon", "email"],
            "sort": "nazwisko_asc",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    text = response.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0] == ["Nazwisko", "Telefon", "E-mail"]
    assert rows[1] == ["'=2+2", "'+48600111222", "'@polecenie.example"]

    audit = db.query(models.AuditLog).filter_by(
        akcja="crm_guest_export",
    ).one()
    assert audit.zasob == "rows:1"
    assert "=2+2" not in (audit.szczegoly or "")
    assert "600111222" not in (audit.szczegoly or "")
    assert "@polecenie.example" not in (audit.szczegoly or "")
    assert '"columns":["nazwisko","telefon","email"]' in audit.szczegoly


def test_legacy_consent_is_unverified_and_withdrawal_cannot_be_resurrected(
    admin_client,
    db,
):
    source, target = _exact_pair(db)
    _profile(db, source, legacy_marketing=True)
    _profile(db, target, legacy_marketing=True)

    legacy = admin_client.get(
        f"/api/crm/rezerwacje/{source.id}/zgody",
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["state"] == "legacy_unverified"
    assert legacy.json()["active"] is False
    assert legacy.json()["legacy_unverified"] is True

    grant = _record_consent(
        admin_client,
        source,
        "grant",
        key="crm-consent-grant-0001",
    )
    grant_replay = _record_consent(
        admin_client,
        source,
        "grant",
        key="crm-consent-grant-0001",
    )
    assert grant.status_code == grant_replay.status_code == 201
    assert grant.json()["state"] == "granted"
    assert grant.json()["active"] is True
    assert grant_replay.json()["replay"] is True

    decline = _record_consent(
        admin_client,
        source,
        "decline",
        key="crm-consent-decline-0001",
        source="operator_email",
    )
    assert decline.status_code == 201
    # Declining a new checkbox is not an explicit withdrawal of an older grant.
    assert decline.json()["state"] == "granted"
    assert decline.json()["active"] is True

    withdrawn = _record_consent(
        admin_client,
        source,
        "withdraw",
        key="crm-consent-withdraw-0001",
        source="operator_phone",
    )
    assert withdrawn.status_code == 201
    assert withdrawn.json()["state"] == "withdrawn"
    assert withdrawn.json()["active"] is False

    target_grant = _record_consent(
        admin_client,
        target,
        "grant",
        key="crm-consent-target-grant-0001",
    )
    assert target_grant.status_code == 201
    merged = _create_merge(
        admin_client,
        source,
        target,
        key="crm-consent-merge-0001",
    )
    assert merged.status_code == 201, merged.text

    after_merge = admin_client.get(
        f"/api/crm/rezerwacje/{source.id}/zgody",
    )
    assert after_merge.status_code == 200
    assert after_merge.json()["state"] == "mixed"
    assert after_merge.json()["active"] is False
    assert db.query(models.CrmConsentEvent).count() == 4

    stale_version = admin_client.post(
        f"/api/crm/rezerwacje/{source.id}/zgody",
        headers={"Idempotency-Key": "crm-consent-stale-version"},
        json={
            "decision": "grant",
            "source": "operator_in_person",
            "document_version": "stale-consent-v0",
        },
    )
    assert stale_version.status_code == 409
    assert admin_client.get(
        f"/api/crm/rezerwacje/{source.id}/zgody",
    ).json()["active"] is False


def test_r73_permissions_are_exact(client, db):
    source, target = _exact_pair(db)
    manage_only = _manager(
        "crm_manage_without_contact",
        "rezerwacje.crm_zarzadzaj",
    )
    contact_only = _manager(
        "crm_contact_without_manage",
        "rezerwacje.dane_kontaktowe",
    )
    manager = _manager(
        "crm_manager_complete",
        "rezerwacje.crm_zarzadzaj",
        "rezerwacje.dane_kontaktowe",
    )
    exporter = _manager(
        "crm_exporter_complete",
        "rezerwacje.eksport",
        "rezerwacje.dane_kontaktowe",
    )

    assert client.get(
        "/api/crm/jakosc",
        headers=_headers(manage_only),
    ).status_code == 403
    assert client.get(
        "/api/crm/jakosc",
        headers=_headers(contact_only),
    ).status_code == 403
    assert client.get(
        "/api/crm/jakosc",
        headers=_headers(manager),
    ).status_code == 200

    assert client.post(
        "/api/crm/eksport",
        headers=_headers(manager),
        json={"columns": ["nazwisko"]},
    ).status_code == 403
    assert client.post(
        "/api/crm/eksport",
        headers=_headers(exporter),
        json={"columns": ["nazwisko"]},
    ).status_code == 200

    assert client.post(
        "/api/crm/scalenia/podglad",
        headers=_headers(exporter),
        json={"source_ref": source.id, "target_ref": target.id},
    ).status_code == 403
    assert client.post(
        "/api/crm/scalenia/podglad",
        headers=_headers(manager),
        json={"source_ref": source.id, "target_ref": target.id},
    ).status_code == 200


def test_crm_search_allows_only_controlled_manager_combinations(client, db):
    _reservation(
        db,
        nazwisko="Gość uprawnień",
        telefon="600123456",
        email="uprawnienia@example.test",
    )
    manage_without_operations = _manager(
        "crm_search_manage_without_operations",
        "rezerwacje.crm_zarzadzaj",
        "rezerwacje.dane_kontaktowe",
    )
    operations_without_scope = _manager(
        "crm_search_operations_without_scope",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
    )
    manage_without_contact = _manager(
        "crm_search_manage_without_contact",
        "rezerwacje.operacje",
        "rezerwacje.crm_zarzadzaj",
    )
    manager = _manager(
        "crm_search_manager_complete",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
        "rezerwacje.crm_zarzadzaj",
    )
    exporter = _manager(
        "crm_search_exporter_complete",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
        "rezerwacje.eksport",
    )
    payload = {"q": "Gość", "limit": 20}

    for denied in (
        manage_without_operations,
        operations_without_scope,
        manage_without_contact,
    ):
        assert client.post(
            "/api/crm/goscie/wyszukaj",
            headers=_headers(denied),
            json=payload,
        ).status_code == 403

    for allowed in (manager, exporter):
        response = client.post(
            "/api/crm/goscie/wyszukaj",
            headers=_headers(allowed),
            json=payload,
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1

    # Historyczny GET pozostaje wyłącznie administracyjny.
    assert client.get(
        "/api/crm/goscie",
        headers=_headers(exporter),
    ).status_code == 403


def test_rodo_erasure_removes_only_direct_consent_and_merge_edges(
    admin_client,
    db,
):
    source, target = _exact_pair(db)
    source_profile = _profile(db, source, note="Tylko źródło")
    target_profile = _profile(db, target, note="Tylko cel")
    now = datetime(2026, 7, 23, 10, 0)
    source_event = models.CrmConsentEvent(
        subject_hash=identity_hash(source),
        purpose="marketing",
        decision="grant",
        document_version=main.PUBLIC_MARKETING_CONSENT_VERSION,
        source="operator_in_person",
        captured_at=now,
        termin_id=source.id,
        actor_login="admin_test",
        event_key_hash="a" * 64,
        request_fingerprint="c" * 64,
        created_at=now,
    )
    target_event = models.CrmConsentEvent(
        subject_hash=identity_hash(target),
        purpose="marketing",
        decision="grant",
        document_version=main.PUBLIC_MARKETING_CONSENT_VERSION,
        source="operator_in_person",
        captured_at=now,
        termin_id=target.id,
        actor_login="admin_test",
        event_key_hash="b" * 64,
        request_fingerprint="d" * 64,
        created_at=now,
    )
    db.add_all([source_event, target_event])
    db.commit()
    db.refresh(source_event)
    db.refresh(target_event)
    source_event_id = source_event.id
    target_event_id = target_event.id
    source_profile_id = source_profile.id
    target_profile_id = target_profile.id

    merged = _create_merge(
        admin_client,
        source,
        target,
        key="crm-rodo-merge-0001",
    )
    assert merged.status_code == 201, merged.text
    assert db.query(models.CrmGuestMerge).count() == 1

    erased = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": "600111222"},
    )

    assert erased.status_code == 200, erased.text
    db.expire_all()
    source_after = db.get(models.Termin, source.id)
    target_after = db.get(models.Termin, target.id)
    assert source_after.nazwisko == "[anonimizacja RODO]"
    assert source_after.telefon is None and source_after.email is None
    assert target_after.nazwisko == "Anna K."
    assert target_after.telefon == "600333444"
    assert target_after.email == "WSPOLNY@example.test"
    assert db.query(models.CrmGuestMerge).count() == 0
    assert db.get(models.CrmConsentEvent, source_event_id) is None
    assert db.get(models.CrmConsentEvent, target_event_id) is not None
    assert db.get(models.ProfilGoscia, source_profile_id) is None
    assert db.get(models.ProfilGoscia, target_profile_id) is not None


def test_consent_authorizes_reservation_scope_before_writing(client, db):
    sala = _reservation(
        db,
        nazwisko="Klient sali",
        telefon="600987654",
        email="sala@example.test",
        rodzaj="sala",
    )
    manager = _manager(
        "crm_manager_sala_scope",
        "rezerwacje.crm_zarzadzaj",
        "rezerwacje.dane_kontaktowe",
    )
    headers = {
        **_headers(manager),
        "Idempotency-Key": "crm-consent-sala-scope-0001",
    }

    response = client.post(
        f"/api/crm/rezerwacje/{sala.id}/zgody",
        headers=headers,
        json={
            "decision": "grant",
            "source": "operator_phone",
            "document_version": main.PUBLIC_MARKETING_CONSENT_VERSION,
        },
    )

    assert response.status_code == 404
    assert db.query(models.CrmConsentEvent).count() == 0
    assert db.query(models.AuditLog).filter_by(
        akcja="crm_consent_event",
    ).count() == 0


def test_public_consent_uses_frozen_subject_and_legacy_null_fails_closed(
    admin_client,
    db,
):
    reservation = _reservation(
        db,
        nazwisko="Zgoda publiczna",
        telefon="600121212",
        email="zgoda@example.test",
    )
    now = datetime(2026, 7, 20, 12, 0)
    consent = models.RezerwacjaZgodaPubliczna(
        termin_id=reservation.id,
        subject_hash=identity_hash(reservation),
        notice_version="privacy-v1",
        notice_ack_at=now,
        marketing=True,
        marketing_version=main.PUBLIC_MARKETING_CONSENT_VERSION,
        marketing_at=now,
        sensitive=False,
        sensitive_version=None,
        sensitive_at=None,
        sensitive_data=None,
        retention_until=now + timedelta(days=365),
        ip_hash="f" * 64,
        created_at=now,
    )
    db.add(consent)
    db.commit()

    before = admin_client.get(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
    )
    assert before.status_code == 200
    assert before.json()["state"] == "granted"
    assert before.json()["active"] is True

    reservation.telefon = "600343434"
    db.commit()
    changed = admin_client.get(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
    )
    assert changed.status_code == 200
    assert changed.json()["state"] == "missing"
    assert changed.json()["active"] is False

    reservation.telefon = "600121212"
    consent.subject_hash = None
    db.commit()
    legacy = admin_client.get(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
    )
    assert legacy.status_code == 200
    assert legacy.json()["state"] == "missing"
    assert legacy.json()["active"] is False


def test_consent_idempotency_fingerprint_distinguishes_explicit_capture_time(
    admin_client,
    db,
):
    reservation = _reservation(
        db,
        nazwisko="Fingerprint",
        telefon="600565656",
        email=None,
    )
    headers = {"Idempotency-Key": "crm-consent-fingerprint-0001"}
    payload = {
        "decision": "grant",
        "source": "operator_in_person",
        "document_version": main.PUBLIC_MARKETING_CONSENT_VERSION,
        "captured_at": "2026-07-20T10:00:00",
    }

    first = admin_client.post(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
        headers=headers,
        json=payload,
    )
    mismatch = admin_client.post(
        f"/api/crm/rezerwacje/{reservation.id}/zgody",
        headers=headers,
        json={**payload, "captured_at": "2026-07-20T10:01:00"},
    )

    assert first.status_code == 201, first.text
    assert mismatch.status_code == 409
    event = db.query(models.CrmConsentEvent).one()
    assert len(event.request_fingerprint) == 64
    assert event.captured_at == datetime(2026, 7, 20, 10, 0)


def test_unique_races_converge_to_merge_and_consent_replays(
    admin_client,
    db,
    monkeypatch,
):
    source, target = _exact_pair(db)
    merge_key = "crm-merge-converge-0001"
    first_merge = _create_merge(
        admin_client,
        source,
        target,
        key=merge_key,
    )
    assert first_merge.status_code == 201, first_merge.text

    with monkeypatch.context() as scoped:
        scoped.setattr(
            crm_governance,
            "create_merge",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                IntegrityError("INSERT", {}, RuntimeError("duplicate")),
            ),
        )
        replay_merge = _create_merge(
            admin_client,
            source,
            target,
            key=merge_key,
        )
    assert replay_merge.status_code == 201, replay_merge.text
    assert replay_merge.json()["replay"] is True

    reservation = _reservation(
        db,
        nazwisko="Replay zgody",
        telefon="600787878",
        email=None,
        day_offset=2,
    )
    consent_key = "crm-consent-converge-0001"
    first_consent = _record_consent(
        admin_client,
        reservation,
        "grant",
        key=consent_key,
    )
    assert first_consent.status_code == 201, first_consent.text

    with monkeypatch.context() as scoped:
        scoped.setattr(
            crm_governance,
            "record_consent",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                IntegrityError("INSERT", {}, RuntimeError("duplicate")),
            ),
        )
        replay_consent = _record_consent(
            admin_client,
            reservation,
            "grant",
            key=consent_key,
        )
    assert replay_consent.status_code == 201, replay_consent.text
    assert replay_consent.json()["replay"] is True
    assert db.query(models.CrmGuestMerge).count() == 1
    assert db.query(models.CrmConsentEvent).count() == 1


def test_contact_change_reverts_merge_only_when_previous_hash_is_orphaned(
    admin_client,
    db,
):
    source, target = _exact_pair(db)
    sibling = _reservation(
        db,
        nazwisko="Anna drugi wpis",
        telefon=source.telefon,
        email=source.email,
        day_offset=2,
    )
    merged = _create_merge(
        admin_client,
        source,
        target,
        key="crm-merge-contact-change-0001",
    )
    assert merged.status_code == 201, merged.text
    merge_id = merged.json()["id"]
    actor = db.query(models.User).filter_by(rola="admin").first()
    previous_key = identity_key(source)

    source.telefon = "600111223"
    assert crm_governance.revert_orphaned_identity_merges_after_contact_change(
        db,
        reservation_id=source.id,
        previous_identity_key=previous_key,
        actor=actor,
    ) == []
    db.commit()
    assert db.get(models.CrmGuestMerge, merge_id).status == "active"

    sibling.telefon = "600111224"
    assert crm_governance.revert_orphaned_identity_merges_after_contact_change(
        db,
        reservation_id=sibling.id,
        previous_identity_key=previous_key,
        actor=actor,
    ) == [merge_id]
    db.commit()
    row = db.get(models.CrmGuestMerge, merge_id)
    assert row.status == "reverted"
    assert row.version == 2
    assert db.query(models.AuditLog).filter_by(
        akcja="crm_guest_merge_contact_change_revert",
    ).count() == 1


def test_retention_preserves_governance_for_hash_with_fresh_reservation(
    admin_client,
    db,
):
    today_offset = (date.today() - DAY).days
    old_target = _reservation(
        db,
        nazwisko="Stara wizyta",
        telefon="600454545",
        email="retencja-wspolny@example.test",
        day_offset=today_offset - 800,
    )
    fresh_target = _reservation(
        db,
        nazwisko="Nowa wizyta",
        telefon="600454545",
        email="retencja-wspolny@example.test",
        day_offset=today_offset,
    )
    source = _reservation(
        db,
        nazwisko="Drugie źródło",
        telefon="600464646",
        email="retencja-wspolny@example.test",
        day_offset=today_offset,
    )
    merged = _create_merge(
        admin_client,
        source,
        fresh_target,
        key="crm-merge-retention-fresh-0001",
    )
    assert merged.status_code == 201, merged.text
    consent = _record_consent(
        admin_client,
        old_target,
        "grant",
        key="crm-consent-retention-fresh-0001",
    )
    assert consent.status_code == 201, consent.text
    event_id = db.query(models.CrmConsentEvent).one().id
    merge_id = merged.json()["id"]

    retained = admin_client.post("/api/rodo/retencja?miesiace=12")

    assert retained.status_code == 200, retained.text
    db.expire_all()
    assert db.get(models.Termin, old_target.id).telefon is None
    assert db.get(models.Termin, fresh_target.id).telefon == "600454545"
    assert db.get(models.CrmConsentEvent, event_id) is not None
    assert db.get(models.CrmGuestMerge, merge_id) is not None


def test_admin_rodo_export_contains_hash_free_crm_provenance(admin_client, db):
    source, target = _exact_pair(db)
    merged = _create_merge(
        admin_client,
        source,
        target,
        key="crm-merge-rodo-export-0001",
    )
    assert merged.status_code == 201, merged.text
    consent = _record_consent(
        admin_client,
        source,
        "grant",
        key="crm-consent-rodo-export-0001",
    )
    assert consent.status_code == 201, consent.text

    response = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": "600111222"},
    )

    assert response.status_code == 200, response.text
    privacy = response.json()["prywatnosc"]
    assert len(privacy["zgody_operatora"]) == 1
    assert privacy["zgody_operatora"][0]["decyzja"] == "grant"
    assert len(privacy["scalenia_crm"]) == 1
    assert privacy["scalenia_crm"][0]["rola_podmiotu"] == ["source"]
    serialized = response.text
    assert identity_hash(source) not in serialized
    assert "source_hash" not in serialized
    assert "target_hash" not in serialized
    assert "event_key_hash" not in serialized
    assert "request_fingerprint" not in serialized
