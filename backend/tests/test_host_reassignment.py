"""R6b.3: atomowy exact-set seat/move dla pointera i klawiatury."""

from datetime import date

import models


DAY = "2026-07-13"


def _table(client, name, capacity):
    response = client.post(
        "/api/stoliki", json={"nazwa": name, "pojemnosc": capacity},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _combination(client, name, tables, *, minimum=1):
    response = client.post("/api/kombinacje", json={
        "nazwa": name,
        "stoliki": [table["id"] for table in tables],
        "pojemnosc_min": minimum,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _reservation(client, *, people=2, table_id=None, name="Gość R6b.3"):
    payload = {
        "data": DAY,
        "godz_od": "18:00",
        "liczba_osob": people,
        "nazwisko": name,
    }
    if table_id is not None:
        payload["stolik_id"] = table_id
    response = client.post("/api/rezerwacje-stolik", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _exact(client, rid, operation, target, expected, key, **extra):
    path = (
        f"/api/host/rezerwacja/{rid}/posadz"
        if operation == "seat"
        else f"/api/host/rezerwacja/{rid}/przydziel-stolik"
    )
    return client.post(
        path,
        headers={"Idempotency-Key": key},
        json={
            "stoliki": [table["id"] if isinstance(table, dict) else table for table in target],
            "oczekiwane_stoliki": [
                table["id"] if isinstance(table, dict) else table for table in expected
            ],
            **extra,
        },
    )


def _seat_on_source(client, *, people=6):
    source = [_table(client, "Źródło 4", 4), _table(client, "Źródło 2", 2)]
    target = [_table(client, "Cel 6", 6), _table(client, "Cel 4", 4)]
    _combination(client, "Źródło 4+2", source, minimum=1)
    _combination(client, "Cel 6+4", target, minimum=1)
    reservation = _reservation(client, people=people)
    seated = _exact(
        client,
        reservation["id"],
        "seat",
        source,
        [],
        f"seat-{reservation['id']}",
    )
    assert seated.status_code == 200, seated.text
    return reservation["id"], source, target, seated


def test_exact_seat_accepts_approved_combination_and_has_no_undo(admin_client, db):
    rid, source, _target, response = _seat_on_source(admin_client)
    body = response.json()
    source_ids = [table["id"] for table in source]

    assert body["mutation"] == {
        "operation": "seat",
        "changed": True,
        "from_stoliki": [],
        "to_stoliki": source_ids,
        "replayed": False,
    }
    assert body["undo_command"] is None
    assert body["przydzial"]["stoliki"] == source_ids
    assert body["allocation"]["state"] == "assigned"
    assert body["allocation"]["kind"] == "combination"
    assert body["rezerwacja"]["faza_hosta"] == "posadzony"

    db.expire_all()
    saved = db.get(models.Termin, rid)
    assert [saved.stolik_id, *(saved.stoliki_dodatkowe or [])] == source_ids
    assert saved.faza_hosta == "posadzony"


def test_exact_move_preserves_phase_and_returns_revalidated_undo(admin_client, db):
    rid, source, target, _seated = _seat_on_source(admin_client)
    db.expire_all()
    seated_at = db.get(models.Termin, rid).host_seated_at

    response = _exact(
        admin_client, rid, "move", target, source, f"move-{rid}",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    source_ids = [table["id"] for table in source]
    target_ids = [table["id"] for table in target]

    assert body["mutation"] == {
        "operation": "move",
        "changed": True,
        "from_stoliki": source_ids,
        "to_stoliki": target_ids,
        "replayed": False,
    }
    assert body["undo_command"] == {
        "path": f"/host/rezerwacja/{rid}/przydziel-stolik",
        "method": "POST",
        "source_version": "tables:" + ",".join(map(str, target_ids)),
        "body": {
            "stoliki": source_ids,
            "oczekiwane_stoliki": target_ids,
        },
    }
    assert body["przydzial"]["stoliki"] == target_ids
    assert body["rezerwacja"]["faza_hosta"] == "posadzony"

    db.expire_all()
    saved = db.get(models.Termin, rid)
    assert [saved.stolik_id, *(saved.stoliki_dodatkowe or [])] == target_ids
    assert saved.faza_hosta == "posadzony"
    assert saved.host_seated_at == seated_at


def test_exact_contract_requires_idempotency_key_and_source_cas(admin_client, db):
    rid, source, target, _seated = _seat_on_source(admin_client)
    target_ids = [table["id"] for table in target]

    missing = admin_client.post(
        f"/api/host/rezerwacja/{rid}/przydziel-stolik",
        json={"stoliki": target_ids, "oczekiwane_stoliki": [table["id"] for table in source]},
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    stale = _exact(
        admin_client, rid, "move", target, [], f"stale-{rid}",
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "HOST_ASSIGNMENT_CHANGED"

    db.expire_all()
    saved = db.get(models.Termin, rid)
    assert [saved.stolik_id, *(saved.stoliki_dodatkowe or [])] == [
        table["id"] for table in source
    ]


def test_exact_move_is_idempotent_and_rejects_key_reuse(admin_client, db):
    rid, source, target, _seated = _seat_on_source(admin_client)
    key = f"move-replay-{rid}"
    first = _exact(admin_client, rid, "move", target, source, key)
    replay = _exact(admin_client, rid, "move", target, source, key)

    assert first.status_code == replay.status_code == 200
    assert first.json()["mutation"]["replayed"] is False
    assert replay.json()["mutation"]["replayed"] is True
    assert replay.json()["mutation"]["to_stoliki"] == [table["id"] for table in target]

    reused = _exact(admin_client, rid, "move", source, target, key)
    assert reused.status_code == 409
    assert reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    db.expire_all()
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=rid, action="assign",
    ).count() == 1


def test_exact_replay_rejects_metadata_stale_after_later_move(admin_client):
    rid, source, target, _seated = _seat_on_source(admin_client)
    later = _table(admin_client, "Późniejszy cel", 6)
    first_key = f"move-stale-replay-{rid}"

    first = _exact(admin_client, rid, "move", target, source, first_key)
    assert first.status_code == 200, first.text
    second = _exact(
        admin_client, rid, "move", [later], target, f"move-later-{rid}",
    )
    assert second.status_code == 200, second.text

    replay = _exact(admin_client, rid, "move", target, source, first_key)
    assert replay.status_code == 409
    assert replay.json()["code"] == "IDEMPOTENCY_RESULT_STALE"
    assert "undo_command" not in replay.json()


def test_exact_move_noop_does_not_touch_day_or_audit(admin_client, db):
    rid, source, _target, _seated = _seat_on_source(admin_client)
    db.expire_all()
    day = date.fromisoformat(DAY)
    before_revision = db.get(models.RezerwacjaDzienLedger, day).revision
    before_audits = db.query(models.ReservationAudit).filter_by(
        termin_id=rid, action="assign",
    ).count()

    response = _exact(
        admin_client, rid, "move", source, source, f"move-noop-{rid}",
    )
    assert response.status_code == 200, response.text
    assert response.json()["mutation"]["changed"] is False
    assert response.json()["undo_command"] is None

    db.expire_all()
    assert db.get(models.RezerwacjaDzienLedger, day).revision == before_revision
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=rid, action="assign",
    ).count() == before_audits


def test_exact_move_conflict_preserves_old_assignment_and_claims(admin_client, db):
    rid, source, _target, _seated = _seat_on_source(admin_client, people=2)
    blocked = _table(admin_client, "Zajęty cel", 4)
    _reservation(admin_client, people=2, table_id=blocked["id"], name="Blokada")

    response = _exact(
        admin_client, rid, "move", [blocked], source, f"move-conflict-{rid}",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "TABLE_CONFLICT"

    db.expire_all()
    saved = db.get(models.Termin, rid)
    source_ids = [table["id"] for table in source]
    assert [saved.stolik_id, *(saved.stoliki_dodatkowe or [])] == source_ids
    claimed = {
        table_id for (table_id,) in db.query(
            models.RezerwacjaStolikClaim.stolik_id,
        ).filter_by(termin_id=rid).distinct().all()
    }
    assert claimed == set(source_ids)
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=rid, action="assign",
    ).count() == 0


def test_exact_move_rejects_unapproved_set_and_terminal_reservation(admin_client, db):
    rid, source, _target, _seated = _seat_on_source(admin_client)
    loose = [_table(admin_client, "Luźny A", 6), _table(admin_client, "Luźny B", 4)]

    invalid = _exact(
        admin_client, rid, "move", loose, source, f"invalid-set-{rid}",
    )
    assert invalid.status_code == 409
    assert invalid.json()["code"] == "INVALID_TABLE_COMBINATION"

    left = admin_client.post(
        f"/api/host/rezerwacja/{rid}/faza", json={"faza": "wyszedl"},
    )
    assert left.status_code == 200, left.text
    terminal = _exact(
        admin_client, rid, "move", loose[:1], source, f"terminal-{rid}",
    )
    assert terminal.status_code == 409
    assert terminal.json()["code"] == "RESERVATION_NOT_ACTIVE"


def test_exact_schema_rejects_duplicates_and_partial_contract(admin_client):
    table = _table(admin_client, "Schema", 4)
    reservation = _reservation(admin_client, table_id=table["id"])
    path = f"/api/host/rezerwacja/{reservation['id']}/posadz"

    duplicate = admin_client.post(
        path,
        headers={"Idempotency-Key": "duplicate-target"},
        json={
            "stoliki": [table["id"], table["id"]],
            "oczekiwane_stoliki": [table["id"]],
        },
    )
    partial = admin_client.post(
        path,
        headers={"Idempotency-Key": "partial-target"},
        json={"stoliki": [table["id"]]},
    )
    bool_identifier = admin_client.post(
        path,
        headers={"Idempotency-Key": "bool-target"},
        json={"stoliki": [True], "oczekiwane_stoliki": [table["id"]]},
    )
    untyped_override = admin_client.post(
        path,
        headers={"Idempotency-Key": "untyped-override"},
        json={
            "stoliki": [table["id"]],
            "oczekiwane_stoliki": [table["id"]],
            "przekrocz_limity": True,
        },
    )

    assert duplicate.status_code == 422
    assert partial.status_code == 422
    assert bool_identifier.status_code == 422
    assert untyped_override.status_code == 422
