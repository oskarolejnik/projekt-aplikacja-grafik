"""R2.2: runtime rezerwacji czyta wyłącznie published snapshot planu sali."""

from datetime import datetime

import main
import models


def _published_room(
    db,
    *,
    with_edge=False,
    combination_channel=None,
    combination_active=True,
    second_active=True,
):
    now = datetime.utcnow()
    room = models.SalaRezerwacyjna(
        nazwa="Sala snapshot",
        nazwa_klucz="sala snapshot",
        aktywna=True,
        kolejnosc=0,
    )
    db.add(room)
    db.flush()
    plan = models.PlanSali(sala_id=room.id, nazwa="Plan sali snapshot")
    db.add(plan)
    db.flush()
    version = models.WersjaPlanuSali(
        plan_id=plan.id,
        numer=1,
        status="published",
        rewizja=0,
        utworzono_at=now,
        zaktualizowano_at=now,
        opublikowano_at=now,
    )
    db.add(version)
    db.flush()

    tables = [
        models.Stolik(
            nazwa="LIVE-A",
            sala_id=room.id,
            strefa=room.nazwa,
            pojemnosc=1,
            aktywny=True,
            kolejnosc=90,
        ),
        models.Stolik(
            nazwa="LIVE-B",
            sala_id=room.id,
            strefa=room.nazwa,
            pojemnosc=1,
            aktywny=True,
            kolejnosc=91,
        ),
    ]
    db.add_all(tables)
    db.flush()
    positions = [
        models.PozycjaStolikaPlanu(
            wersja_id=version.id,
            stolik_id=table.id,
            plan_x=10 + index * 20,
            plan_y=20,
            szerokosc=12,
            wysokosc=12,
            obrot=0,
            aktywny_w_planie=second_active if index else True,
            nazwa=f"SNAP-{chr(65 + index)}",
            kolejnosc=index,
            pojemnosc=4,
            pojemnosc_min=1,
            ksztalt="kwadrat",
            cechy=["okno"] if index == 0 else ["cicho"],
            priorytet=index,
            sekcja="Snapshot sekcja",
        )
        for index, table in enumerate(tables)
    ]
    db.add_all(positions)
    db.flush()

    edge = None
    if with_edge:
        edge = models.KrawedzSasiedztwaPlanu(
            wersja_id=version.id,
            stolik_a_id=tables[0].id,
            stolik_b_id=tables[1].id,
        )
        db.add(edge)

    combination = None
    if combination_channel is not None:
        combination = models.KombinacjaStolowPlanu(
            wersja_id=version.id,
            nazwa="Published combo",
            sklad_klucz=",".join(str(table.id) for table in tables),
            pojemnosc_min=5,
            pojemnosc_max=8,
            priorytet=0,
            kanal=combination_channel,
            aktywna_w_planie=combination_active,
        )
        db.add(combination)
        db.flush()
        db.add_all([
            models.SkladnikKombinacjiPlanu(
                kombinacja_id=combination.id,
                wersja_id=version.id,
                stolik_id=table.id,
            )
            for table in tables
        ])
    db.commit()
    return {
        "room": room,
        "plan": plan,
        "version": version,
        "tables": tables,
        "edge": edge,
        "combination": combination,
    }


def _legacy_table(db, name, capacity=4):
    table = models.Stolik(
        nazwa=name,
        pojemnosc=capacity,
        aktywny=True,
        kolejnosc=0,
    )
    db.add(table)
    db.flush()
    return table


def test_published_adjacency_never_generates_runtime_combination(admin_client, db):
    setup = _published_room(db, with_edge=True)

    response = admin_client.get(
        "/api/host/sugestia-stolika?data=2026-07-13&godz_od=18:00&osoby=8"
    )

    assert response.status_code == 200, response.text
    assert response.json()["kandydaci"] == []
    assert main._sasiedztwo_do_seating(db) == []
    assert {row["id"] for row in main._stoly_do_seating(db)} == {
        table.id for table in setup["tables"]
    }


def test_only_active_published_combination_works_and_channel_is_respected(
    admin_client, db,
):
    setup = _published_room(db, combination_channel="oba")
    table_ids = [table.id for table in setup["tables"]]

    response = admin_client.get(
        "/api/host/sugestia-stolika?data=2026-07-13&godz_od=18:00&osoby=8"
    )
    assert response.status_code == 200, response.text
    assert response.json()["kandydaci"][0]["stoliki"] == table_ids
    assert response.json()["kandydaci"][0]["nazwa"] == "Published combo"

    setup["combination"].kanal = "online"
    db.commit()
    assert main._kombinacje_do_seating(db, kanal="wewnetrzna") == []
    assert [row["stoliki"] for row in main._kombinacje_do_seating(
        db, kanal="online",
    )] == [table_ids]

    setup["combination"].aktywna_w_planie = False
    db.commit()
    assert main._kombinacje_do_seating(db, kanal="online") == []


def test_legacy_tables_and_adjacency_remain_runtime_fallback(admin_client):
    first = admin_client.post(
        "/api/stoliki", json={"nazwa": "Legacy A", "pojemnosc": 4},
    ).json()
    second = admin_client.post(
        "/api/stoliki", json={"nazwa": "Legacy B", "pojemnosc": 4},
    ).json()
    edge = admin_client.post(
        "/api/sasiedztwo",
        json={"stolik_a": first["id"], "stolik_b": second["id"]},
    )
    assert edge.status_code == 201, edge.text

    response = admin_client.get(
        "/api/host/sugestia-stolika?data=2026-07-13&godz_od=18:00&osoby=8"
    )
    assert response.status_code == 200, response.text
    assert response.json()["kandydaci"][0]["stoliki"] == [
        first["id"], second["id"],
    ]


def test_legacy_writes_touching_versioned_room_are_blocked(admin_client, db):
    setup = _published_room(db)
    versioned = setup["tables"][0]
    legacy = _legacy_table(db, "Legacy outside")
    stale_combination = models.KombinacjaStolow(
        nazwa="Stale cross-room combo",
        stoliki=[versioned.id, legacy.id],
        pojemnosc_min=1,
        pojemnosc_max=8,
        aktywna=True,
        priorytet=0,
    )
    stale_edge = models.SasiedztwoStolow(
        stolik_a=min(versioned.id, legacy.id),
        stolik_b=max(versioned.id, legacy.id),
    )
    db.add_all([stale_combination, stale_edge])
    db.commit()

    responses = [
        admin_client.post(
            "/api/kombinacje",
            json={
                "nazwa": "Blocked",
                "stoliki": [versioned.id, legacy.id],
            },
        ),
        admin_client.put(
            f"/api/kombinacje/{stale_combination.id}",
            json={
                "nazwa": "Blocked edit",
                "stoliki": [versioned.id, legacy.id],
            },
        ),
        admin_client.delete(f"/api/kombinacje/{stale_combination.id}"),
        admin_client.post(
            "/api/sasiedztwo",
            json={"stolik_a": versioned.id, "stolik_b": legacy.id},
        ),
        admin_client.delete(f"/api/sasiedztwo/{stale_edge.id}"),
    ]
    for response in responses:
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"


def test_legacy_gets_project_published_snapshot_and_hide_draft_or_stale_data(
    admin_client, db,
):
    setup = _published_room(
        db,
        with_edge=True,
        combination_channel="oba",
        second_active=False,
    )
    first, second = setup["tables"]
    legacy_a = _legacy_table(db, "Legacy A")
    legacy_b = _legacy_table(db, "Legacy B")
    stale_combo = models.KombinacjaStolow(
        nazwa="Stale cross-room combo",
        stoliki=[first.id, legacy_a.id],
        pojemnosc_min=1,
        pojemnosc_max=8,
        aktywna=True,
        priorytet=0,
    )
    legacy_combo = models.KombinacjaStolow(
        nazwa="Legacy combo",
        stoliki=[legacy_a.id, legacy_b.id],
        pojemnosc_min=1,
        pojemnosc_max=8,
        aktywna=False,
        priorytet=3,
    )
    stale_edge = models.SasiedztwoStolow(
        stolik_a=min(first.id, legacy_a.id),
        stolik_b=max(first.id, legacy_a.id),
    )
    legacy_edge = models.SasiedztwoStolow(
        stolik_a=min(legacy_a.id, legacy_b.id),
        stolik_b=max(legacy_a.id, legacy_b.id),
    )
    db.add_all([stale_combo, legacy_combo, stale_edge, legacy_edge])
    db.flush()

    draft = models.WersjaPlanuSali(
        plan_id=setup["plan"].id,
        numer=2,
        status="draft",
        rewizja=0,
        utworzono_at=datetime.utcnow(),
        zaktualizowano_at=datetime.utcnow(),
    )
    draft_only = models.Stolik(
        nazwa="DRAFT ONLY",
        sala_id=setup["room"].id,
        strefa=setup["room"].nazwa,
        pojemnosc=12,
        aktywny=False,
        kolejnosc=0,
    )
    db.add_all([draft, draft_only])
    db.flush()
    db.add(models.PozycjaStolikaPlanu(
        wersja_id=draft.id,
        stolik_id=draft_only.id,
        plan_x=50,
        plan_y=50,
        szerokosc=12,
        wysokosc=12,
        obrot=0,
        aktywny_w_planie=True,
        nazwa="Draft snapshot",
        kolejnosc=0,
        pojemnosc=12,
    ))
    db.commit()

    tables = admin_client.get("/api/stoliki").json()["stoliki"]
    by_id = {table["id"]: table for table in tables}
    assert set(by_id) == {first.id, second.id, legacy_a.id, legacy_b.id}
    assert by_id[first.id]["nazwa"] == "SNAP-A"
    assert by_id[first.id]["pojemnosc"] == 4
    assert by_id[second.id]["aktywny"] is False
    assert draft_only.id not in by_id

    combinations = admin_client.get("/api/kombinacje").json()["kombinacje"]
    assert {row["nazwa"] for row in combinations} == {
        "Published combo", "Legacy combo",
    }
    assert next(row for row in combinations if row["nazwa"] == "Legacy combo")[
        "aktywna"
    ] is False

    edges = admin_client.get("/api/sasiedztwo").json()["krawedzie"]
    edge_pairs = {(row["stolik_a"], row["stolik_b"]) for row in edges}
    assert edge_pairs == {
        (first.id, second.id),
        (min(legacy_a.id, legacy_b.id), max(legacy_a.id, legacy_b.id)),
    }


def test_legacy_read_adapter_namespaces_colliding_snapshot_ids(admin_client, db):
    setup = _published_room(
        db,
        with_edge=True,
        combination_channel="oba",
    )
    legacy_a = _legacy_table(db, "Legacy namespace A")
    legacy_b = _legacy_table(db, "Legacy namespace B")
    legacy_combination = models.KombinacjaStolow(
        nazwa="Legacy namespace combo",
        stoliki=[legacy_a.id, legacy_b.id],
        pojemnosc_min=1,
        pojemnosc_max=8,
        aktywna=True,
        priorytet=2,
    )
    legacy_edge = models.SasiedztwoStolow(
        stolik_a=min(legacy_a.id, legacy_b.id),
        stolik_b=max(legacy_a.id, legacy_b.id),
    )
    db.add_all([legacy_combination, legacy_edge])
    db.commit()

    snapshot_combination_id = setup["combination"].id
    snapshot_edge_id = setup["edge"].id
    assert snapshot_combination_id == legacy_combination.id
    assert snapshot_edge_id == legacy_edge.id

    combinations = admin_client.get("/api/kombinacje").json()["kombinacje"]
    snapshot_combination = next(
        row for row in combinations if row["nazwa"] == "Published combo"
    )
    legacy_combination_row = next(
        row for row in combinations if row["nazwa"] == "Legacy namespace combo"
    )
    assert snapshot_combination["id"] == -snapshot_combination_id
    assert legacy_combination_row["id"] == legacy_combination.id

    edges = admin_client.get("/api/sasiedztwo").json()["krawedzie"]
    snapshot_edge = next(
        row for row in edges
        if {row["stolik_a"], row["stolik_b"]}
        == {table.id for table in setup["tables"]}
    )
    legacy_edge_row = next(
        row for row in edges
        if {row["stolik_a"], row["stolik_b"]} == {legacy_a.id, legacy_b.id}
    )
    assert snapshot_edge["id"] == -snapshot_edge_id
    assert legacy_edge_row["id"] == legacy_edge.id

    rejected_edit = admin_client.put(
        f"/api/kombinacje/{snapshot_combination['id']}",
        json={
            "nazwa": "Nie moze trafic w legacy",
            "stoliki": [legacy_a.id, legacy_b.id],
        },
    )
    assert rejected_edit.status_code == 404
    assert admin_client.delete(
        f"/api/kombinacje/{snapshot_combination['id']}",
    ).status_code == 204
    assert admin_client.delete(
        f"/api/sasiedztwo/{snapshot_edge['id']}",
    ).status_code == 204

    db.expire_all()
    assert db.get(models.KombinacjaStolow, legacy_combination.id).nazwa == (
        "Legacy namespace combo"
    )
    assert db.get(models.SasiedztwoStolow, legacy_edge.id) is not None


def test_versioned_table_direct_edit_allows_only_pos_link(admin_client, db):
    setup = _published_room(db)
    table = setup["tables"][0]
    canonical = next(
        row for row in admin_client.get("/api/stoliki").json()["stoliki"]
        if row["id"] == table.id
    )
    assert canonical["nazwa"] == "SNAP-A"
    assert table.nazwa == "LIVE-A"

    pos_payload = {key: value for key, value in canonical.items() if key != "id"}
    pos_payload["rewir_nr"] = 17
    updated = admin_client.put(f"/api/stoliki/{table.id}", json=pos_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["rewir_nr"] == 17
    db.expire_all()
    assert db.get(models.Stolik, table.id).rewir_nr == 17
    assert db.get(models.Stolik, table.id).nazwa == "LIVE-A"

    blocked_payload = dict(pos_payload)
    blocked_payload["pojemnosc"] = 6
    blocked = admin_client.put(f"/api/stoliki/{table.id}", json=blocked_payload)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"


def test_legacy_assignment_without_provenance_survives_combination_retirement(db):
    setup = _published_room(db)
    table_ids = [table.id for table in setup["tables"]]

    # Przydziały utworzone przed R2.2b nie mają wiarygodnej proweniencji.
    # Zachowujemy je bez zgadywania wersji na podstawie samych identyfikatorów stołów.
    main._waliduj_rozmiar_zachowanej_kombinacji(db, table_ids, 7)


def test_inactive_room_is_excluded_from_new_host_online_and_auto_candidates(
    admin_client, client, db,
):
    setup = _published_room(db, combination_channel="oba")
    table_ids = {table.id for table in setup["tables"]}
    setup["room"].aktywna = False
    db.commit()

    assert not (table_ids & {row["id"] for row in main._stoly_do_seating(db)})
    assert main._kombinacje_do_seating(db, kanal="wewnetrzna") == []
    assert main._kombinacje_do_seating(db, kanal="online") == []

    suggestion = admin_client.get(
        "/api/host/sugestia-stolika?data=2035-07-16&godz_od=18:00&osoby=2"
    )
    assert suggestion.status_code == 200, suggestion.text
    assert suggestion.json()["kandydaci"] == []

    reservation = admin_client.post("/api/rezerwacje-stolik", json={
        "data": "2035-07-16",
        "godz_od": "18:00",
        "liczba_osob": 2,
        "nazwisko": "Bez aktywnej sali",
    })
    assert reservation.status_code == 201, reservation.text
    auto = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation.json()['id']}/auto-przydziel"
    )
    assert auto.status_code == 409, auto.text
    assert "Brak wolnego stołu" in auto.json()["detail"]

    assert admin_client.put(
        "/api/lokal/config", json={"rezerwacje_online": True},
    ).status_code == 200
    service = admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": 0,
        "godz_od": "17:00",
        "godz_do": "21:00",
        "dlugosc_slotu_min": 60,
    })
    assert service.status_code == 201, service.text
    slots = client.get(
        "/api/online/dostepnosc?data=2035-07-16&osoby=2"
    ).json()["sloty"]
    assert slots
    assert all(slot["wolne"] == 0 and slot["wolne_stoly"] == 0 for slot in slots)

    # Wyłączenie sali zmienia pulę nowych przydziałów, nie usuwa opublikowanej
    # konfiguracji z adapterów odczytowych.
    assert table_ids <= {
        row["id"] for row in admin_client.get("/api/stoliki").json()["stoliki"]
    }
    assert "Published combo" in {
        row["nazwa"]
        for row in admin_client.get("/api/kombinacje").json()["kombinacje"]
    }


def test_public_availability_respects_snapshot_table_minimum(
    admin_client,
    client,
    db,
):
    setup = _published_room(db, second_active=False)
    position = db.query(models.PozycjaStolikaPlanu).filter_by(
        wersja_id=setup["version"].id,
        stolik_id=setup["tables"][0].id,
    ).one()
    position.pojemnosc = 6
    position.pojemnosc_min = 4
    db.commit()

    assert admin_client.put(
        "/api/lokal/config",
        json={"rezerwacje_online": True},
    ).status_code == 200
    service = admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": 0,
        "godz_od": "17:00",
        "godz_do": "21:00",
        "dlugosc_slotu_min": 60,
    })
    assert service.status_code == 201, service.text

    too_small = client.get(
        "/api/online/dostepnosc?data=2035-07-16&osoby=2",
    )
    assert too_small.status_code == 200, too_small.text
    assert too_small.json()["sloty"]
    assert all(
        slot["wolne"] == 0 and slot["wolne_stoly"] == 0
        for slot in too_small.json()["sloty"]
    )

    matching = client.get(
        "/api/online/dostepnosc?data=2035-07-16&osoby=4",
    )
    assert matching.status_code == 200, matching.text
    assert matching.json()["sloty"]
    assert all(
        slot["wolne"] == 1 and slot["wolne_stoly"] == 1
        for slot in matching.json()["sloty"]
    )


def test_inactive_room_keeps_assigned_table_on_operational_timeline(
    admin_client, db,
):
    setup = _published_room(db)
    assigned, unassigned = setup["tables"]
    reservation = admin_client.post("/api/rezerwacje-stolik", json={
        "data": "2035-07-16",
        "godz_od": "18:00",
        "stolik_id": assigned.id,
        "liczba_osob": 2,
        "nazwisko": "Historyczny przydział",
    })
    assert reservation.status_code == 201, reservation.text

    setup["room"].aktywna = False
    db.commit()

    timeline = admin_client.get(
        "/api/host/os-czasu?data=2035-07-16"
    )
    assert timeline.status_code == 200, timeline.text
    payload = timeline.json()
    by_id = {row["id"]: row for row in payload["stoly"]}
    assert by_id[assigned.id]["nazwa"] == "SNAP-A"
    assert unassigned.id not in by_id
    assert any(
        row["rezerwacja_id"] == reservation.json()["id"]
        and row["stolik_id"] == assigned.id
        for row in payload["zajetosci"]
    )

    updated = admin_client.put(
        f"/api/rezerwacje-stolik/{reservation.json()['id']}",
        json={
            "data": "2035-07-16",
            "godz_od": "18:00",
            "stolik_id": assigned.id,
            "liczba_osob": 2,
            "nazwisko": "Historyczny przydział — aktualizacja",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["stolik_id"] == assigned.id
    assert updated.json()["nazwisko"] == "Historyczny przydział — aktualizacja"


def test_explicit_null_snapshot_properties_never_revive_legacy_values(db):
    setup = _published_room(db)
    table = setup["tables"][0]
    position = db.query(models.PozycjaStolikaPlanu).filter_by(
        wersja_id=setup["version"].id,
        stolik_id=table.id,
    ).one()
    table.pojemnosc_min = 3
    table.ksztalt = "okragly"
    table.cechy = ["loza"]
    table.priorytet = 99
    table.sekcja = "Legacy sekcja"
    position.pojemnosc_min = None
    position.ksztalt = None
    position.cechy = None
    position.priorytet = None
    position.sekcja = None
    db.commit()

    read_row = next(
        row for row in main._stoliki_do_odczytu(db) if row["id"] == table.id
    )
    assert read_row["pojemnosc_min"] is None
    assert read_row["ksztalt"] is None
    assert read_row["cechy"] is None
    assert read_row["priorytet"] is None
    assert read_row["sekcja"] is None

    runtime_row = next(
        row for row in main._stoly_do_seating(db) if row["id"] == table.id
    )
    assert runtime_row["pojemnosc_min"] is None
    assert runtime_row["ksztalt"] is None
    assert runtime_row["cechy"] == []
    assert runtime_row["priorytet"] == 0
    assert runtime_row["sekcja"] == setup["room"].nazwa
