"""R2.2b: strategie sal i niezmienna proweniencja przydziału."""

from datetime import date, datetime, time, timedelta

import main
import models


def _published_room(
    db,
    name,
    capacities,
    *,
    strategy="preferuj",
    priority=0,
    order=0,
    combination_range=None,
):
    now = datetime.utcnow()
    room = models.SalaRezerwacyjna(
        nazwa=name,
        nazwa_klucz=name.casefold(),
        aktywna=True,
        kolejnosc=order,
        strategia_zapelniania=strategy,
        priorytet=priority,
    )
    db.add(room)
    db.flush()
    plan = models.PlanSali(sala_id=room.id, nazwa=f"Plan {name}")
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
    tables = []
    for index, capacity in enumerate(capacities):
        table = models.Stolik(
            nazwa=f"{name}-{index + 1}",
            sala_id=room.id,
            strefa=name,
            pojemnosc=capacity,
            aktywny=True,
            kolejnosc=index,
        )
        db.add(table)
        db.flush()
        tables.append(table)
        db.add(models.PozycjaStolikaPlanu(
            wersja_id=version.id,
            stolik_id=table.id,
            plan_x=15 + index * 25,
            plan_y=25,
            szerokosc=12,
            wysokosc=12,
            obrot=0,
            aktywny_w_planie=True,
            nazwa=table.nazwa,
            kolejnosc=index,
            pojemnosc=capacity,
            pojemnosc_min=1,
            priorytet=0,
            sekcja=name,
        ))
    combination = None
    if combination_range is not None:
        db.flush()
        db.add(models.KrawedzSasiedztwaPlanu(
            wersja_id=version.id,
            stolik_a_id=tables[0].id,
            stolik_b_id=tables[1].id,
        ))
        combination = models.KombinacjaStolowPlanu(
            wersja_id=version.id,
            nazwa=f"{name} zestaw",
            sklad_klucz=",".join(str(table.id) for table in tables),
            pojemnosc_min=combination_range[0],
            pojemnosc_max=combination_range[1],
            priorytet=0,
            kanal="oba",
            aktywna_w_planie=True,
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
    return room, plan, version, tables, combination


def _replace_published_combination(db, setup, allowed_range):
    room, plan, old_version, tables, _old_combination = setup
    now = datetime.utcnow()
    old_version.status = "retired"
    version = models.WersjaPlanuSali(
        plan_id=plan.id,
        numer=2,
        status="published",
        rewizja=0,
        utworzono_at=now,
        zaktualizowano_at=now,
        opublikowano_at=now,
    )
    db.add(version)
    db.flush()
    for index, table in enumerate(tables):
        db.add(models.PozycjaStolikaPlanu(
            wersja_id=version.id,
            stolik_id=table.id,
            plan_x=15 + index * 25,
            plan_y=25,
            szerokosc=12,
            wysokosc=12,
            obrot=0,
            aktywny_w_planie=True,
            nazwa=table.nazwa,
            kolejnosc=index,
            pojemnosc=table.pojemnosc,
            pojemnosc_min=1,
            priorytet=0,
            sekcja=room.nazwa,
        ))
    db.flush()
    db.add(models.KrawedzSasiedztwaPlanu(
        wersja_id=version.id,
        stolik_a_id=tables[0].id,
        stolik_b_id=tables[1].id,
    ))
    combination = models.KombinacjaStolowPlanu(
        wersja_id=version.id,
        nazwa="Nowy węższy zestaw",
        sklad_klucz=",".join(str(table.id) for table in tables),
        pojemnosc_min=allowed_range[0],
        pojemnosc_max=allowed_range[1],
        priorytet=0,
        kanal="oba",
        aktywna_w_planie=True,
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
    return version, combination


def test_room_strategy_contract_preserves_fields_for_older_put(admin_client):
    created = admin_client.post("/api/sale-rezerwacyjne", json={
        "nazwa": "Sala priorytetowa",
        "aktywna": True,
        "kolejnosc": 4,
        "strategia_zapelniania": "wypelniaj_kolejno",
        "priorytet": 2,
    })
    assert created.status_code == 201, created.text
    assert created.json()["strategia_zapelniania"] == "wypelniaj_kolejno"
    assert created.json()["priorytet"] == 2

    legacy_put = admin_client.put(
        f"/api/sale-rezerwacyjne/{created.json()['id']}",
        json={"nazwa": "Sala priorytetowa", "aktywna": True, "kolejnosc": 5},
    )
    assert legacy_put.status_code == 200, legacy_put.text
    assert legacy_put.json()["strategia_zapelniania"] == "wypelniaj_kolejno"
    assert legacy_put.json()["priorytet"] == 2

    invalid = admin_client.put(
        f"/api/sale-rezerwacyjne/{created.json()['id']}",
        json={
            "nazwa": "Sala priorytetowa",
            "strategia_zapelniania": "balansuj",
        },
    )
    assert invalid.status_code == 422


def test_runtime_wypelnia_pierwsza_scisla_sale_przed_lepszym_best_fit(db):
    first = _published_room(
        db, "Pierwsza", [8], strategy="wypelniaj_kolejno", priority=0, order=3,
    )
    _published_room(
        db, "Druga", [4], strategy="wypelniaj_kolejno", priority=1, order=0,
    )
    _published_room(db, "Miekka", [4], strategy="preferuj", priority=0)

    chosen = main._wybierz_wolny_przydzial(
        db,
        date.today() + timedelta(days=30),
        time(18, 0),
        time(20, 0),
        4,
    )

    assert chosen["stoliki"] == [first[3][0].id]
    assert chosen["sala_id"] == first[0].id
    assert chosen["strategia_zapelniania"] == "wypelniaj_kolejno"


def test_auto_allocation_keeps_retired_combination_provenance_and_manual_clears_it(
    admin_client, db,
):
    setup = _published_room(db, "Historia", [4, 4], combination_range=(5, 8))
    _room, _plan, old_version, tables, old_combination = setup
    reservation = models.Termin(
        data=date.today() + timedelta(days=40),
        nazwisko="Gość historyczny",
        liczba_osob=6,
        status="potwierdzona",
        zadatek=0,
        utworzono_at=datetime.utcnow(),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        rodzaj="stolik",
        kanal="reczna",
    )
    db.add(reservation)
    db.commit()

    assigned = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation.id}/auto-przydziel",
    )
    assert assigned.status_code == 200, assigned.text
    db.refresh(reservation)
    assert reservation.przydzial_wersja_planu_id == old_version.id
    assert reservation.przydzial_kombinacja_planu_id == old_combination.id
    assert assigned.json()["rezerwacja"]["przydzial_wersja_planu_id"] == old_version.id
    assert assigned.json()["przydzial"]["kombinacja_planu_id"] == old_combination.id

    _replace_published_combination(db, setup, (5, 6))
    edited = admin_client.put(
        f"/api/rezerwacje-stolik/{reservation.id}",
        json={
            "data": str(reservation.data),
            "godz_od": "18:00",
            "godz_do": "20:00",
            "stolik_id": tables[0].id,
            "liczba_osob": 8,
            "nazwisko": reservation.nazwisko,
            "zadatek": 0,
        },
    )
    assert edited.status_code == 200, edited.text
    db.refresh(reservation)
    assert reservation.przydzial_wersja_planu_id == old_version.id
    assert reservation.przydzial_kombinacja_planu_id == old_combination.id

    manual_room = _published_room(db, "Manualna", [8])
    manual = admin_client.post(
        f"/api/host/rezerwacja/{reservation.id}/przydziel-stolik",
        json={"stolik_id": manual_room[3][0].id},
    )
    assert manual.status_code == 200, manual.text
    db.refresh(reservation)
    assert reservation.stoliki_dodatkowe is None
    assert reservation.przydzial_wersja_planu_id is None
    assert reservation.przydzial_kombinacja_planu_id is None
