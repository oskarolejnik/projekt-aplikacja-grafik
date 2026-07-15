"""R2.2: wersjonowane wlasciwosci stolow i topologia planu sali."""

from datetime import date, datetime, time, timedelta

import models
from deps import _teraz_lokalnie


def _room(admin_client, name="Sala R2.2"):
    response = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": name, "aktywna": True, "kolejnosc": 0},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _table(db, room, name, capacity=4, **extra):
    table = models.Stolik(
        nazwa=name,
        sala_id=room["id"],
        strefa=room["nazwa"],
        pojemnosc=capacity,
        aktywny=True,
        kolejnosc=db.query(models.Stolik).count(),
        **extra,
    )
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


def _positions(plan, overrides=None, *, properties=True):
    overrides = overrides or {}
    rows = []
    for table in plan["stoliki"]:
        row = {
            "stolik_id": table["id"],
            "plan_x": table["plan_x"],
            "plan_y": table["plan_y"],
            "szerokosc": table["szerokosc"],
            "wysokosc": table["wysokosc"],
            "obrot": table["obrot"],
            "aktywny_w_planie": table["aktywny_w_planie"],
        }
        if properties:
            row.update({
                "nazwa": table["nazwa"],
                "kolejnosc": table["kolejnosc"],
                "pojemnosc": table["pojemnosc"],
                "pojemnosc_min": table["pojemnosc_min"],
                "ksztalt": table["ksztalt"],
                "cechy": table["cechy"],
                "priorytet": table["priorytet"],
                "sekcja": table["sekcja"],
            })
        row.update(overrides.get(table["id"], {}))
        rows.append(row)
    return rows


def _draft(admin_client, room):
    response = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    )
    assert response.status_code == 200, response.text
    return response.json()


def _save(admin_client, room, payload):
    return admin_client.put(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
        json=payload,
    )


def test_topology_is_isolated_published_cloned_and_used_by_runtime(admin_client, db):
    room = _room(admin_client)
    first = _table(db, room, "S1", cechy=["okno"])
    second = _table(db, room, "S2")
    third = _table(db, room, "S3")
    draft = _draft(admin_client, room)

    assert draft["krawedzie"] == []
    assert draft["kombinacje"] == []
    saved = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft, {
            first.id: {
                "nazwa": "Stolik premium",
                "pojemnosc": 2,
                "pojemnosc_min": 1,
                "ksztalt": "okragly",
                "cechy": ["okno", "cichy"],
                "priorytet": -2,
                "sekcja": "A",
            },
        }),
        "krawedzie": [
            {"stolik_a_id": second.id, "stolik_b_id": first.id},
            {"stolik_a_id": second.id, "stolik_b_id": third.id},
        ],
        "kombinacje": [{
            "nazwa": "Duzy stol",
            "stoliki": [third.id, first.id, second.id],
            "pojemnosc_min": 5,
            "pojemnosc_max": 10,
            "priorytet": 1,
            "kanal": "oba",
            "aktywna_w_planie": True,
        }],
    })
    assert saved.status_code == 200, saved.text
    saved_body = saved.json()
    assert saved_body["krawedzie"] == [
        {"stolik_a_id": first.id, "stolik_b_id": second.id},
        {"stolik_a_id": second.id, "stolik_b_id": third.id},
    ]
    assert saved_body["kombinacje"][0]["stoliki"] == sorted(
        [first.id, second.id, third.id],
    )

    public_before = admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan",
    ).json()
    assert public_before["stoliki"] == []
    assert public_before["krawedzie"] == []
    assert public_before["kombinacje"] == []

    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert published.status_code == 200, published.text
    db.expire_all()
    live = db.get(models.Stolik, first.id)
    assert live.nazwa == "Stolik premium"
    assert live.pojemnosc == 2
    assert live.cechy == ["okno", "cichy"]
    assert live.sekcja == "A"

    runtime = admin_client.get(
        f"/api/plan-sali?sala_id={room['id']}",
    ).json()
    assert next(row for row in runtime["stoliki"] if row["id"] == first.id)[
        "nazwa"
    ] == "Stolik premium"
    assert runtime["kombinacje"][0]["stoliki"] == sorted(
        [first.id, second.id, third.id],
    )

    clone = _draft(admin_client, room)
    assert clone["krawedzie"] == saved_body["krawedzie"]
    assert clone["kombinacje"][0]["stoliki"] == saved_body["kombinacje"][0]["stoliki"]
    changed = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(clone, {
            first.id: {"nazwa": "Tylko szkic"},
        }),
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["krawedzie"] == clone["krawedzie"]
    assert admin_client.get(
        f"/api/plan-sali?sala_id={room['id']}",
    ).json()["stoliki"][0]["nazwa"] != "Tylko szkic"
    assert admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan",
    ).json()["stoliki"][0]["nazwa"] != "Tylko szkic"
    discarded = admin_client.delete(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic?expected_revision=1",
    )
    assert discarded.status_code == 204, discarded.text
    assert admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan",
    ).json()["krawedzie"] == saved_body["krawedzie"]


def test_heterogeneous_combinations_use_sum_of_snapshot_capacities_in_runtime(
    admin_client,
    db,
):
    room = _room(admin_client)
    four = _table(db, room, "S4", capacity=4)
    two = _table(db, room, "S2", capacity=2)
    six = _table(db, room, "S6", capacity=6)
    draft = _draft(admin_client, room)

    saved = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft),
        "krawedzie": [
            {"stolik_a_id": four.id, "stolik_b_id": two.id},
            {"stolik_a_id": six.id, "stolik_b_id": four.id},
        ],
        "kombinacje": [
            {
                "nazwa": "Cztery plus dwa",
                "stoliki": [four.id, two.id],
                "pojemnosc_min": 5,
            },
            {
                "nazwa": "Szesc plus cztery",
                "stoliki": [six.id, four.id],
                "pojemnosc_min": 7,
            },
        ],
    })
    assert saved.status_code == 200, saved.text
    assert {
        row["nazwa"]: row["pojemnosc_max"]
        for row in saved.json()["kombinacje"]
    } == {
        "Cztery plus dwa": 6,
        "Szesc plus cztery": 10,
    }

    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert published.status_code == 200, published.text

    runtime = admin_client.get(
        f"/api/plan-sali?sala_id={room['id']}",
    )
    assert runtime.status_code == 200, runtime.text
    assert {
        row["nazwa"]: row["pojemnosc_max"]
        for row in runtime.json()["kombinacje"]
    } == {
        "Cztery plus dwa": 6,
        "Szesc plus cztery": 10,
    }

    for people, expected_name, expected_ids, expected_capacity in (
        (6, "Cztery plus dwa", [four.id, two.id], 6),
        (10, "Szesc plus cztery", [six.id, four.id], 10),
    ):
        suggestion = admin_client.get(
            "/api/host/sugestia-stolika",
            params={
                "data": "2035-07-15",
                "godz_od": "18:00",
                "osoby": people,
            },
        )
        assert suggestion.status_code == 200, suggestion.text
        candidate = next(
            row
            for row in suggestion.json()["kandydaci"]
            if row["nazwa"] == expected_name
        )
        assert candidate["stoliki"] == sorted(expected_ids)
        assert candidate["suma_pojemnosci"] == expected_capacity
        assert candidate["kombinacja"] is True


def test_omitted_topology_is_preserved_and_empty_arrays_clear_it(admin_client, db):
    room = _room(admin_client)
    first = _table(db, room, "S1")
    second = _table(db, room, "S2")
    draft = _draft(admin_client, room)
    initial = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft),
        "krawedzie": [{"stolik_a_id": first.id, "stolik_b_id": second.id}],
        "kombinacje": [{
            "nazwa": "S1 + S2",
            "stoliki": [first.id, second.id],
            "pojemnosc_min": 2,
            "pojemnosc_max": 8,
        }],
    })
    assert initial.status_code == 200, initial.text

    legacy_pwa = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(initial.json(), properties=False),
    })
    assert legacy_pwa.status_code == 200, legacy_pwa.text
    assert legacy_pwa.json()["krawedzie"] == initial.json()["krawedzie"]
    assert legacy_pwa.json()["kombinacje"][0]["stoliki"] == [first.id, second.id]

    cleared = _save(admin_client, room, {
        "expected_revision": 2,
        "pozycje": _positions(legacy_pwa.json(), properties=False),
        "krawedzie": [],
        "kombinacje": [],
    })
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["krawedzie"] == []
    assert cleared.json()["kombinacje"] == []


def test_explicit_null_clears_nullable_properties_and_omission_preserves_it(
    admin_client,
    db,
):
    room = _room(admin_client)
    table = _table(
        db,
        room,
        "S1",
        ksztalt="okragly",
        cechy=["okno"],
        priorytet=3,
        sekcja="A",
    )
    draft = _draft(admin_client, room)

    cleared = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft, {
            table.id: {
                "nazwa": None,
                "kolejnosc": None,
                "pojemnosc": None,
                "ksztalt": None,
                "cechy": None,
                "priorytet": None,
                "sekcja": None,
            },
        }),
    })
    assert cleared.status_code == 200, cleared.text
    cleared_table = cleared.json()["stoliki"][0]
    assert {
        field: cleared_table[field]
        for field in ("ksztalt", "cechy", "priorytet", "sekcja")
    } == {
        "ksztalt": None,
        "cechy": None,
        "priorytet": None,
        "sekcja": None,
    }
    assert cleared_table["nazwa"] == "S1"
    assert cleared_table["kolejnosc"] == table.kolejnosc
    assert cleared_table["pojemnosc"] == 4

    preserved = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(cleared.json(), properties=False),
    })
    assert preserved.status_code == 200, preserved.text
    preserved_table = preserved.json()["stoliki"][0]
    assert {
        field: preserved_table[field]
        for field in ("ksztalt", "cechy", "priorytet", "sekcja")
    } == {
        "ksztalt": None,
        "cechy": None,
        "priorytet": None,
        "sekcja": None,
    }

    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 2},
    )
    assert published.status_code == 200, published.text
    runtime_table = admin_client.get(
        f"/api/plan-sali?sala_id={room['id']}",
    ).json()["stoliki"][0]
    assert runtime_table["ksztalt"] is None
    assert runtime_table["cechy"] == []
    assert runtime_table["priorytet"] is None
    assert runtime_table["sekcja"] is None


def test_full_put_preserves_legacy_capacity_above_fifty(admin_client, db):
    room = _room(admin_client)
    table = _table(db, room, "Sala bankietowa", capacity=64, pojemnosc_min=24)
    draft = _draft(admin_client, room)
    assert draft["stoliki"][0]["pojemnosc"] == 64

    unchanged = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft),
    })

    assert unchanged.status_code == 200, unchanged.text
    saved_table = unchanged.json()["stoliki"][0]
    assert saved_table["id"] == table.id
    assert saved_table["pojemnosc"] == 64
    assert saved_table["pojemnosc_min"] == 24


def test_invalid_topology_and_duplicate_names_are_atomic(admin_client, db):
    room = _room(admin_client)
    first = _table(db, room, "S1")
    second = _table(db, room, "S2")
    third = _table(db, room, "S3")
    other_room = _room(admin_client, "Inna sala")
    foreign = _table(db, other_room, "O1")
    draft = _draft(admin_client, room)
    valid = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft),
        "krawedzie": [{"stolik_a_id": first.id, "stolik_b_id": second.id}],
        "kombinacje": [{
            "nazwa": "Para",
            "stoliki": [first.id, second.id],
            "pojemnosc_min": 2,
            "pojemnosc_max": 8,
        }],
    })
    assert valid.status_code == 200, valid.text
    baseline = valid.json()

    disconnected = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline, {first.id: {"plan_x": 99}}),
        "krawedzie": [{"stolik_a_id": first.id, "stolik_b_id": second.id}],
        "kombinacje": [{
            "nazwa": "Niespojna",
            "stoliki": [first.id, third.id],
            "pojemnosc_min": 2,
            "pojemnosc_max": 8,
        }],
    })
    assert disconnected.status_code == 422
    assert disconnected.json()["detail"]["code"] == "PLAN_TOPOLOGY_INVALID"

    reversed_duplicate = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline),
        "krawedzie": [
            {"stolik_a_id": first.id, "stolik_b_id": second.id},
            {"stolik_a_id": second.id, "stolik_b_id": first.id},
        ],
        "kombinacje": baseline["kombinacje"],
    })
    assert reversed_duplicate.status_code == 422

    cross_room = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline),
        "krawedzie": [{"stolik_a_id": first.id, "stolik_b_id": foreign.id}],
        "kombinacje": [],
    })
    assert cross_room.status_code == 422

    active_with_inactive_member = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline, {
            second.id: {"aktywny_w_planie": False},
        }),
        "krawedzie": baseline["krawedzie"],
        "kombinacje": baseline["kombinacje"],
    })
    assert active_with_inactive_member.status_code == 422

    impossible_capacity = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline),
        "krawedzie": baseline["krawedzie"],
        "kombinacje": [{
            "nazwa": "Za duza",
            "stoliki": [first.id, second.id],
            "pojemnosc_min": 2,
            "pojemnosc_max": 9,
        }],
    })
    assert impossible_capacity.status_code == 422

    duplicate_composition = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline),
        "krawedzie": baseline["krawedzie"],
        "kombinacje": [
            {
                "nazwa": "Pierwsza",
                "stoliki": [first.id, second.id],
                "pojemnosc_min": 2,
                "pojemnosc_max": 8,
            },
            {
                "nazwa": "Druga",
                "stoliki": [second.id, first.id],
                "pojemnosc_min": 2,
                "pojemnosc_max": 8,
            },
        ],
    })
    assert duplicate_composition.status_code == 422

    duplicate_name = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline, {
            second.id: {"nazwa": "  s1  "},
        }),
    })
    assert duplicate_name.status_code == 422
    assert duplicate_name.json()["detail"]["code"] == "PLAN_TABLE_NAME_CONFLICT"

    blank_name = _save(admin_client, room, {
        "expected_revision": 1,
        "pozycje": _positions(baseline, {
            second.id: {"nazwa": "   "},
        }),
    })
    assert blank_name.status_code == 422

    after = admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    assert after["wersja"]["rewizja"] == 1
    assert next(row for row in after["stoliki"] if row["id"] == first.id)[
        "plan_x"
    ] == next(row for row in baseline["stoliki"] if row["id"] == first.id)["plan_x"]
    assert after["krawedzie"] == baseline["krawedzie"]
    assert after["kombinacje"] == baseline["kombinacje"]


def test_publish_blocks_capacity_reduction_for_exact_assignment_and_hold(admin_client, db):
    room = _room(admin_client)
    first = _table(db, room, "S1")
    second = _table(db, room, "S2")
    initial = _draft(admin_client, room)
    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": initial["wersja"]["rewizja"]},
    )
    assert published.status_code == 200, published.text

    draft = _draft(admin_client, room)
    reduced = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft, {
            first.id: {"pojemnosc": 3},
            second.id: {"pojemnosc": 3},
        }),
    })
    assert reduced.status_code == 200, reduced.text

    reservation = models.Termin(
        data=date.today() + timedelta(days=1),
        nazwisko="Rezerwacja",
        rodzaj="stolik",
        status="potwierdzona",
        godz_od=time(18, 0),
        stolik_id=first.id,
        stoliki_dodatkowe=[second.id],
        liczba_osob=7,
    )
    db.add(reservation)
    waitlist = models.ListaOczekujacych(
        data=date.today(),
        godz_od=time(19, 0),
        liczba_osob=4,
        nazwisko="Hold",
        status="oczekuje",
        utworzono_at=datetime.utcnow(),
    )
    db.add(waitlist)
    db.flush()
    local_now = _teraz_lokalnie() or datetime.now()
    claim = models.RezerwacjaStolikClaim(
        waitlist_id=waitlist.id,
        stolik_id=first.id,
        data=date.today(),
        minute=19 * 60,
        expires_at=local_now + timedelta(minutes=10),
        created_at=datetime.utcnow(),
    )
    db.add(claim)
    db.commit()

    conflict = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert conflict.status_code == 409, conflict.text
    detail = conflict.json()["detail"]
    assert detail["code"] == "PLAN_PUBLISH_CONFLICT"
    assert detail["reservation_ids"] == [reservation.id]
    assert detail["hold_ids"] == [claim.id]
    assert detail["table_ids"] == sorted([first.id, second.id])
    db.expire_all()
    assert db.get(models.Stolik, first.id).pojemnosc == 4
    assert db.get(models.Stolik, second.id).pojemnosc == 4
    assert admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan",
    ).json()["stoliki"][0]["pojemnosc"] == 4


def test_publish_blocks_combination_range_outside_exact_reservation_and_hold(
    admin_client,
    db,
):
    room = _room(admin_client)
    first = _table(db, room, "S6", capacity=6)
    second = _table(db, room, "S4", capacity=4)
    overlapping = _table(db, room, "S4B", capacity=4)
    initial = _draft(admin_client, room)
    configured = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(initial),
        "krawedzie": [{
            "stolik_a_id": first.id,
            "stolik_b_id": second.id,
        }],
        "kombinacje": [{
            "nazwa": "Dziesiec miejsc",
            "stoliki": [first.id, second.id],
            "pojemnosc_min": 5,
            "pojemnosc_max": 10,
            "kanal": "oba",
            "aktywna_w_planie": True,
        }],
    })
    assert configured.status_code == 200, configured.text
    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert published.status_code == 200, published.text

    reservation = models.Termin(
        data=date.today() + timedelta(days=1),
        nazwisko="Dziewiec osob",
        rodzaj="stolik",
        status="potwierdzona",
        godz_od=time(18, 0),
        stolik_id=first.id,
        stoliki_dodatkowe=[second.id],
        liczba_osob=9,
    )
    overlapping_reservation = models.Termin(
        data=date.today() + timedelta(days=1),
        nazwisko="Inny zestaw",
        rodzaj="stolik",
        status="potwierdzona",
        godz_od=time(21, 0),
        stolik_id=first.id,
        stoliki_dodatkowe=[overlapping.id],
        liczba_osob=9,
    )
    below_new_minimum = models.Termin(
        data=date.today() + timedelta(days=1),
        nazwisko="Ponizej nowego minimum",
        rodzaj="stolik",
        status="potwierdzona",
        godz_od=time(16, 0),
        stolik_id=first.id,
        stoliki_dodatkowe=[second.id],
        liczba_osob=6,
    )
    waitlist = models.ListaOczekujacych(
        data=date.today(),
        godz_od=time(19, 0),
        liczba_osob=9,
        nazwisko="Hold zestawu",
        status="oczekuje",
        utworzono_at=datetime.utcnow(),
    )
    db.add_all([
        reservation,
        overlapping_reservation,
        below_new_minimum,
        waitlist,
    ])
    db.flush()
    local_now = _teraz_lokalnie() or datetime.now()
    claims = [
        models.RezerwacjaStolikClaim(
            waitlist_id=waitlist.id,
            stolik_id=table_id,
            data=date.today(),
            minute=19 * 60,
            expires_at=local_now + timedelta(minutes=10),
            created_at=datetime.utcnow(),
        )
        for table_id in (first.id, second.id)
    ]
    db.add_all(claims)
    db.commit()

    draft = _draft(admin_client, room)
    reduced = _save(admin_client, room, {
        "expected_revision": 0,
        "pozycje": _positions(draft),
        "krawedzie": draft["krawedzie"],
        "kombinacje": [{
            "nazwa": "Tylko osiem miejsc",
            "stoliki": [first.id, second.id],
            "pojemnosc_min": 7,
            "pojemnosc_max": 8,
            "kanal": "oba",
            "aktywna_w_planie": True,
        }],
    })
    assert reduced.status_code == 200, reduced.text

    conflict = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert conflict.status_code == 409, conflict.text
    detail = conflict.json()["detail"]
    assert detail["code"] == "PLAN_PUBLISH_CONFLICT"
    assert detail["reservation_ids"] == sorted([
        reservation.id,
        below_new_minimum.id,
    ])
    assert overlapping_reservation.id not in detail["reservation_ids"]
    assert detail["hold_ids"] == sorted(claim.id for claim in claims)
    assert detail["table_ids"] == sorted([first.id, second.id])

    still_published = admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan",
    ).json()
    assert still_published["kombinacje"][0]["pojemnosc_max"] == 10
    still_draft = admin_client.get(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    assert still_draft["kombinacje"][0]["pojemnosc_max"] == 8
